from flask import Flask, render_template, request, redirect
import asyncpg
import asyncio

app = Flask(__name__)
db_pool = None  # Pool de banco de dados global

async def create_pool():
    return await asyncpg.create_pool(
        user='postgres',
        password='hd1450',
        database='vinivazado',
        host='localhost',
        port=5432
    )

@app.before_first_request
def init_db_pool():
    global db_pool
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    db_pool = loop.run_until_complete(create_pool())

@app.route('/', methods=['GET', 'POST'])
async def index():
    if request.method == 'POST':
        # Obter dados do formulário
        plano_name = request.form['name']
        plano_price = request.form['price']
        plano_length = request.form['length']

        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO planos (name, price, length) VALUES ($1, $2, $3)",
                plano_name, plano_price, plano_length
            )

        return redirect('/')

    # Buscar planos do banco de dados
    async with db_pool.acquire() as conn:
        planos = await conn.fetch("SELECT * FROM planos")
    return render_template('index.html', planos=planos)

if __name__ == '__main__':
    app.run(debug=True)
