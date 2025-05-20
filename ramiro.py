import asyncio
import requests
import uuid
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext, State
from aiogram.dispatcher import Router

API_TOKEN = "SEU_TOKEN_AQUI"
PUSHINPAY_TOKEN = "SEU_PUSHINPAY_TOKEN_AQUI"

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()

class FunnelStates:
    start = State()
    waiting_for_response1 = State()
    waiting_for_response2 = State()

async def genPixLinkNormal(value, uid):
    print(f"Tentando gerar código Pix para o usuário {uid} no valor de {value}.")
    idempotency_key = str(uuid.uuid4())
    
    url = 'https://api.pushinpay.com.br/api/pix/cashIn'
    headers = {
        "Authorization": f"Bearer {PUSHINPAY_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "value": value,
        "webhook_url": "http://seuservico.com/webhook",  # Atualize para o seu webhook
        "idempotency_key": idempotency_key
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code != 200:
            print(f"Erro ao chamar a API: {response.status_code} - {response.text}")
            return None, None

        data = response.json()
        if 'id' not in data or 'qr_code' not in data:
            raise Exception("Erro ao gerar o código PIX, verifique a resposta da API.")
        
        return data['qr_code'], data['id']

    except Exception as e:
        print(f"Erro ao gerar o link Pix: {e}")
        return None, None

@dp.message_handler(commands=['start'], state='*')
async def start_funnel(message: types.Message, state: FSMContext):
    await message.answer("🙌 Olá! Vamos começar o nosso funil.")
    
    await state.set_state(FunnelStates.waiting_for_response1)
    
    await message.answer("🗣 Mensagem 1: Como você está? Responda para continuar.")

@dp.message_handler(state=FunnelStates.waiting_for_response1)
async def first_response(message: types.Message, state: FSMContext):
    await message.answer("👍 Obrigado pela sua resposta!")
    await message.answer("💬 Mensagem 2: Você gostaria de saber mais sobre algo específico?")
    
    await state.set_state(FunnelStates.waiting_for_response2)

@dp.message_handler(state=FunnelStates.waiting_for_response2)
async def second_response(message: types.Message, state: FSMContext):
    await message.answer("😊 Ótimo! Vamos para a próxima etapa.")
    
    await message.answer("🔔 Mensagem 3: Aqui estão algumas informações úteis.")
    await message.answer("📌 Mensagem 4: Se precisar de ajuda, só avisar!")
    await message.answer("🚀 Mensagem 5: Agora, para acessar conteúdos exclusivos, você pode fazer um pagamento.")

    # Aqui você pode escolher o valor que deve ser enviado ao gerar o Pix
    value_cents = 1990  # exemplo: R$ 19,90
    qr_code, txid = await genPixLinkNormal(value_cents, message.from_user.id)

    if qr_code and txid:
        await message.answer("✅ Prontinho! Copie e pague usando o código Pix abaixo:\n<code>{}</code>".format(qr_code), parse_mode="HTML")
        # Você pode também enviar a mensagem com instruções sobre como usar o Pix.
        await message.answer("✅ Para pagar, use a opção Pix Copia e Cola no seu aplicativo bancário.")
    else:
        await message.answer("❌ Ocorreu um erro ao gerar o código Pix.")

    # Reseta o estado após finalização do funil
    await state.finish()

async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
