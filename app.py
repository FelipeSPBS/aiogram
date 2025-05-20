import asyncio
import os
import requests
import qrcode
import io
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import CommandStart
from aiogram import Router
import asyncpg
from constants import API_TOKEN, PUSHINPAY_TOKEN

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

db_pool = None

# Banco de dados
async def create_pool():
    try:
        return await asyncpg.create_pool(
            user='postgres',
            password='hd1450',
            database='vinivazado',
            host='localhost',
            port=5432
        )
    except Exception as e:
        print(f"Erro ao conectar ao banco de dados: {e}")
        return None

async def create_tables(db_pool):
    try:
        async with db_pool.acquire() as conn:
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                chat_id BIGINT,
                nome TEXT,
                txid TEXT,
                expires INTEGER,
                plano TEXT,
                status TEXT DEFAULT 'Não assinante'
            )
            """)
            print("Tabela de usuários criada com sucesso.")

            await conn.execute("""
            CREATE TABLE IF NOT EXISTS vendas (
                id SERIAL PRIMARY KEY,
                txid TEXT,
                user_id TEXT,
                plano TEXT,
                valor FLOAT,
                status TEXT DEFAULT 'Não Pago',
                origem TEXT DEFAULT 'normal',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            print("Tabela de vendas criada com sucesso.")
    except Exception as e:
        print(f"Erro ao criar tabelas: {e}")

# Planos
plano1 = {"name": "VIP MENSAL", "length": 10, "price": 1990}
plano2 = {"name": "VIP VITALÍCIO", "length": 10, "price": 4990}


def choose_plan_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{plano1['name']} - R$ {plano1['price'] / 100:.2f}", callback_data=f"{plano1['price']}-plan")],
        [InlineKeyboardButton(text=f"{plano2['name']} - R$ {plano2['price'] / 100:.2f}", callback_data=f"{plano2['price']}-plan")]
    ])

@router.message(CommandStart())
async def start(msg: types.Message):
    user_id = str(msg.from_user.id)
    first_name = msg.from_user.first_name
    chat_id = msg.chat.id

    async def insert_user_if_not_exists():
        try:
            async with db_pool.acquire() as conn:
                result = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
                if result is None:
                    await conn.execute("INSERT INTO users (user_id, chat_id, nome) VALUES ($1, $2, $3)", user_id, chat_id, first_name)
        except Exception as e:
            print(f"Erro ao inserir usuário: {e}")

    async def send_image_with_caption():
        video_path = "start.mp4"
        if not os.path.exists(video_path):
            print("Vídeo não encontrado.")
            return

        caption = (
            "Tenha acesso a conteúdos adultos de todas as famosas que você sempre sonhou em ver! 🔥\n\n"
            "👉Onlyfans 😈\n"
            "👉Privacy 😈\n"
            "👉Vazados das famosas 😈\n"
            "👉Xvideos Red 😈\n"
            "👉PornHub Premium 😈\n"
            "👉Tiktokers +18 😈\n\n"
            "Tudo isso e muito mais de forma exclusiva e com altíssima qualidade. 🔥\n\n"
            "Escolha seu plano e venha fazer parte da maior comunidade privada adulta do telegram!\n"
        )

        await bot.send_video(
            chat_id=chat_id,
            video=FSInputFile(video_path),
            caption=caption,
            reply_markup=choose_plan_keyboard(),
            parse_mode="HTML"
        )


    try:
        await asyncio.gather(
            insert_user_if_not_exists(),
            send_image_with_caption()
        )
    except Exception as e:
        print(f"Erro ao enviar imagem inicial: {e}")


@router.callback_query(lambda cb: cb.data.endswith('-plan'))
async def handle_plan_selection(cb: types.CallbackQuery):
    user_id = str(cb.from_user.id)
    chat_id = cb.message.chat.id
    plan_price = int(cb.data.split('-')[0])

    plan_name = plano1['name'] if plan_price == plano1['price'] else plano2['name'] if plan_price == plano2['price'] else None
    if not plan_name:
        await cb.answer("❌ O plano selecionado não é válido.")
        return

    success, txid = await generate_pix_and_notify(plan_price, user_id, chat_id, plan_name, origem='normal')
    if success:
        await check_payment_and_send_downsell(user_id, chat_id, txid)

@router.callback_query(lambda cb: cb.data.endswith('-downsell'))
async def handle_downsell_selection(cb: types.CallbackQuery):
    user_id = str(cb.from_user.id)
    chat_id = cb.message.chat.id
    plan_price = int(cb.data.split('-')[0])

    plan_name = plano1['name'] if plan_price in [int(plano1['price'] * (1 - d)) for d in [0.5, 0.6, 0.8]] \
        else plano2['name'] if plan_price in [int(plano2['price'] * (1 - d)) for d in [0.5, 0.6, 0.8]] \
        else None

    if not plan_name:
        await cb.answer("❌ O plano selecionado não é válido.")
        return

    success, txid = await generate_pix_and_notify(plan_price, user_id, chat_id, plan_name, origem='downsell')
    if success:
        await cb.answer("✅ Pix gerado com desconto!")

@router.callback_query(lambda cb: cb.data.startswith('upgrade_'))
async def handle_upsell(cb: types.CallbackQuery):
    user_id = str(cb.from_user.id)
    chat_id = cb.message.chat.id

    upgrades = {
        "upgrade_vip": {"name": "Upgrade VIP", "price": 4990},
        "upgrade_premium": {"name": "Plano Premium", "price": 8990}
    }

    upgrade = upgrades.get(cb.data)
    if not upgrade:
        await cb.answer("❌ Upgrade inválido.")
        return

    success, txid = await generate_pix_and_notify(upgrade['price'], user_id, chat_id, upgrade['name'], origem='upsell')
    if success:
        await cb.answer("✅ Pix gerado para o upgrade!")

async def generate_pix_and_notify(value_cents, user_id, chat_id, plan_name, origem='normal'):
    try:
        url = "https://api.pushinpay.com.br/api/pix/cashIn"
        headers = {
            "Authorization": f"Bearer {PUSHINPAY_TOKEN}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        payload = {
            "value": value_cents,
            "webhook_url": "http://seuservico.com/webhook"
        }

        response = requests.post(url, headers=headers, json=payload)
        response_data = response.json()

        if response.status_code != 200 or 'qr_code' not in response_data:
            print("Erro ao gerar o código Pix:", response_data)
            return False, None

        pix_code = response_data['qr_code']
        txid = response_data.get('id', None)

        await bot.send_message(chat_id,
            f"🌟 Você selecionou o seguinte plano:\n\n"
            f"🎁 Plano: {plan_name}\n"
            f"💰 Valor: R$ {value_cents / 100:.2f}\n\n"
            f"🔹 Pague via Pix Copia e Cola:\n"
            f"<code>{pix_code}</code>\n"
            f"👉 Toque na chave PIX acima para copiá-la",
            parse_mode="HTML"
        )

        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO vendas (txid, user_id, plano, valor, status, origem) VALUES ($1, $2, $3, $4, $5, $6)",
                txid, user_id, plan_name, value_cents / 100, 'Não Pago', origem
            )

        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Verificar Status do Pagamento", callback_data="checkMyPayment")]
        ])
        await bot.send_message(chat_id, "Após o pagamento, clique no botão abaixo para verificar o status:", reply_markup=markup)
        return True, txid
    except Exception as e:
        print(f"Erro ao gerar o código Pix: {e}")
        await bot.send_message(chat_id, "❌ Erro ao gerar o link Pix, tente novamente mais tarde.")
        return False, None

@router.callback_query(lambda cb: cb.data == "checkMyPayment")
async def check_payment_status(cb: types.CallbackQuery):
    user_id = str(cb.from_user.id)
    chat_id = cb.message.chat.id

    async with db_pool.acquire() as conn:
        txid = await conn.fetchval("SELECT txid FROM vendas WHERE user_id = $1 ORDER BY created_at DESC LIMIT 1", user_id)

    if not txid:
        await cb.answer("❌ Nenhum pagamento encontrado para verificar.")
        return

    url = f'https://api.pushinpay.com.br/api/transactions/{txid}'
    headers = {
        "Authorization": f"Bearer {PUSHINPAY_TOKEN}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    try:
        response = requests.get(url, headers=headers)
        response_data = response.json()
        if response.status_code == 200 and 'status' in response_data:
            payment_status = response_data['status']
            async with db_pool.acquire() as conn:
                if payment_status == 'PAGO':
                    await conn.execute("UPDATE vendas SET status = $1 WHERE txid = $2", 'Pago', txid)
                    await cb.answer("✅ O pagamento foi confirmado como PAGO.")
                else:
                    await cb.answer("❌ O pagamento ainda não foi realizado.")
        else:
            await cb.answer("❌ Não foi possível verificar o status do pagamento.")
    except Exception as e:
        print(f"Erro ao verificar pagamento: {e}")
        await cb.answer("❌ Erro ao verificar o pagamento.")

async def check_payment_and_send_downsell(user_id, chat_id, txid):
    await asyncio.sleep(600)
    query = "SELECT status, origem FROM vendas WHERE txid = $1 LIMIT 1"
    record = await db_pool.fetchrow(query, txid)

    if not record:
        print(f"Nenhuma venda encontrada com txid: {txid}")
        return

    status = record["status"]
    origem = record["origem"]

    if status.lower() == "pago":
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔼 Upgrade VIP - R$ 49,90", callback_data="upgrade_vip")],
            [InlineKeyboardButton(text="🔼 Plano Premium - R$ 89,90", callback_data="upgrade_premium")]
        ])
        await bot.send_message(chat_id, "✅ Pagamento confirmado!\n\n🎉 Você desbloqueou ofertas exclusivas!\n📦 Que tal turbinar sua experiência com estes upgrades?\n", reply_markup=markup)
        return

    if origem != 'normal':
        print("Downsell não aplicado, origem:", origem)
        return

    downsell_offers = [
        {"discount": 0.30, "message": "Oi, tudo bem? Percebi que você gerou o Pix, mas ainda não finalizou. Qualquer dúvida, estou aqui pra te ajudar!"},
        {"discount": 0.40, "message": "Seu acesso ao Grupo VIP está reservado, mas o pagamento ainda não foi confirmado. Assim que o Pix cair, você já entra! 🌟"},
        {"discount": 0.50, "message": "Temos poucas vagas restantes com o bônus ativo. Não deixe pra depois... 😬"},
        {"discount": 0.60, "message": "meu irmão mais velho disse que me levaria ao parque , mas só se eu retribuísse o favor dando minha bucetinha para ele..vou escrever no meu diário que hoje me divertir muito 💗"},
        {"discount": 0.70, "message": "Antes você só conseguia engolir até a metade, mas olha para você agora..engolindo o pau do papai feito uma putinha. Por isso tenho orgulho de dizer para todos que você é minha princesa..a princesinha do papai ¹ ⁸ ⁺"},
        {"discount": 0.80, "message": "🚨 Oferta final liberada!\n\n🔥 80% de desconto nos planos, só agora!"}
    ]


    for offer in downsell_offers:
        d1 = int(plano1['price'] * (1 - offer['discount']))
        d2 = int(plano2['price'] * (1 - offer['discount']))
        
        desconto_percentual = int(offer['discount'] * 100)

        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"{plano1['name']} - R$ {d1 / 100:.2f} - {desconto_percentual}% OFF", callback_data=f"{d1}-downsell")],
            [InlineKeyboardButton(text=f"{plano2['name']} - R$ {d2 / 100:.2f} - {desconto_percentual}% OFF", callback_data=f"{d2}-downsell")]
        ])
        await bot.send_message(chat_id, offer["message"], reply_markup=markup)
        await asyncio.sleep(10)


async def main():
    global db_pool
    db_pool = await create_pool()
    if not db_pool:
        print("Falha ao inicializar o pool do banco de dados. Encerrando...")
        return
    await create_tables(db_pool)
    print("Bot iniciado com sucesso.")
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Erro no loop principal: {e}")




