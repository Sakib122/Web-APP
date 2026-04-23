import os
import asyncio
import datetime
from fastapi import FastAPI, Body
from fastapi.responses import HTMLResponse
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from motor.motor_asyncio import AsyncIOMotorClient
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import uvicorn
from bson import ObjectId

# --- কনফিগারেশন (Environment Variables) ---
TOKEN = os.getenv("BOT_TOKEN")
MONGO_URL = os.getenv("MONGO_URI")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
APP_URL = os.getenv("APP_URL")

bot = Bot(token=TOKEN)
dp = Dispatcher()
app = FastAPI()
scheduler = AsyncIOScheduler()

# MongoDB কানেকশন
client = AsyncIOMotorClient(MONGO_URL)
db = client['movie_database']

# --- ১. বটের কাজ (Admin vs User Logic) ---

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    
    # অ্যাডমিন ডিটেইলস
    if user_id == ADMIN_ID:
        admin_text = (
            "👋 **স্বাগতম অ্যাডমিন!**\n\n"
            "আপনি এখান থেকে নতুন মুভি বা ফাইল অ্যাপে যুক্ত করতে পারবেন।\n\n"
            "📥 **কিভাবে মুভি অ্যাড করবেন:**\n"
            "১. যেকোনো ফাইল (Document/Video) সরাসরি এই বটে পাঠান।\n"
            "২. ফাইলটি পাঠানোর সময় ক্যাপশনে লিখুন:\n"
            "   `মুভির নাম | পোস্টার ইমেজ লিঙ্ক` \n\n"
            "✅ **উদাহরণ:**\n"
            "`Bachelor Point S04 | https://example.com/poster.jpg`"
        )
        kb = [[types.InlineKeyboardButton(text="🎬 ওপেন মুভি অ্যাপ (Preview)", web_app=types.WebAppInfo(url=APP_URL))]]
        markup = types.InlineKeyboardMarkup(inline_keyboard=kb)
        await message.answer(admin_text, reply_markup=markup, parse_mode="Markdown")
        
    # ইউজার ডিটেইলস
    else:
        user_text = (
            f"👋 হ্যালো **{message.from_user.first_name}**!\n\n"
            "🎬 আমাদের মুভি বটে আপনাকে স্বাগতম। এখান থেকে আপনি মুভি বা সিরিজ সহজেই আপনার ইনবক্সে নিতে পারবেন।\n\n"
            "📖 **ব্যবহার করার নিয়ম:**\n"
            "১. নিচে দেওয়া **'ওপেন মুভি অ্যাপ'** বাটনে ক্লিক করুন।\n"
            "২. অ্যাপ থেকে আপনার পছন্দের মুভিটি সার্চ করে পোস্টারে ক্লিক করুন।\n"
            "৩. ১০ সেকেন্ড অ্যাড লোড হবে, তারপর ফাইলটি আপনার ইনবক্সে চলে আসবে।\n\n"
            "⚠️ **মনে রাখবেন:** আপনার ইনবক্সে পাঠানো ফাইলটি ২৪ ঘণ্টা পর অটো ডিলিট হয়ে যাবে।"
        )
        kb = [[types.InlineKeyboardButton(text="🎬 ওপেন মুভি অ্যাপ", web_app=types.WebAppInfo(url=APP_URL))]]
        markup = types.InlineKeyboardMarkup(inline_keyboard=kb)
        await message.answer(user_text, reply_markup=markup, parse_mode="Markdown")

@dp.message(F.document)
@dp.message(F.video)
async def handle_admin_upload(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    
    try:
        caption = message.caption
        if "|" not in caption:
            await message.answer("❌ ফরম্যাট ভুল! দয়া করে এভাবে লিখুন:\n`মুভির নাম | পোস্টার লিঙ্ক`")
            return
            
        title, thumb = caption.split("|")
        file_id = message.document.file_id if message.document else message.video.file_id
        
        movie_data = {
            "title": title.strip(),
            "thumbnail": thumb.strip(),
            "file_id": file_id,
            "created_at": datetime.datetime.utcnow()
        }
        await db.movies.insert_one(movie_data)
        await message.answer("✅ অভিনন্দন! মুভিটি সফলভাবে অ্যাপে যুক্ত হয়েছে।")
    except Exception as e:
        await message.answer(f"⚠️ এরর: {str(e)}")

# --- ২. অটো ডিলিট টাস্ক (২৪ ঘণ্টা পর) ---
async def delete_expired_files():
    now = datetime.datetime.utcnow()
    expired = db.auto_delete.find({"delete_at": {"$lte": now}})
    async for item in expired:
        try:
            await bot.delete_message(item['chat_id'], item['message_id'])
        except: pass
        await db.auto_delete.delete_one({"_id": item['_id']})

# --- ৩. ওয়েব অ্যাপ (উন্নত প্রিমিয়াম ডিজাইন) ---

@app.get("/", response_class=HTMLResponse)
async def ui():
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Moviee BD</title>
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ background: #0b0f1a; color: #fff; font-family: 'Segoe UI', sans-serif; }}
            
            header {{ display: flex; justify-content: space-between; align-items: center; padding: 15px 20px; background: rgba(13,17,23,0.9); backdrop-filter: blur(10px); position: sticky; top: 0; z-index: 1000; border-bottom: 1px solid #1e293b; }}
            .logo {{ font-size: 22px; font-weight: 800; }}
            .logo span {{ background: #e11d48; padding: 2px 6px; border-radius: 5px; font-size: 14px; margin-left: 5px; }}
            
            .user-profile {{ display: flex; align-items: center; gap: 8px; background: #1e293b; padding: 5px 12px; border-radius: 30px; border: 1px solid #334155; }}
            .user-profile img {{ width: 28px; height: 28px; border-radius: 50%; border: 2px solid #38bdf8; }}
            .user-profile span {{ font-size: 13px; font-weight: 500; }}

            .search-section {{ padding: 20px; }}
            .search-input {{ width: 100%; padding: 15px; border-radius: 12px; border: 1px solid #334155; background: #111827; color: white; outline: none; }}

            .movie-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; padding: 0 20px 20px; }}
            .movie-card {{ background: #111827; border-radius: 12px; overflow: hidden; position: relative; aspect-ratio: 2/3; border: 1px solid #1f2937; box-shadow: 0 10px 20px rgba(0,0,0,0.5); }}
            .movie-card img {{ width: 100%; height: 100%; object-fit: cover; }}
            .movie-info {{ position: absolute; bottom: 0; width: 100%; background: linear-gradient(transparent, rgba(0,0,0,0.9)); padding: 15px 5px 8px; text-align: center; font-size: 14px; font-weight: 500; }}

            .ad-overlay {{ position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: #000; display: none; flex-direction: column; align-items: center; justify-content: center; z-index: 10000; }}
            .timer {{ width: 100px; height: 100px; border-radius: 50%; border: 5px solid #e11d48; display: flex; align-items: center; justify-content: center; font-size: 40px; font-weight: bold; color: #e11d48; margin-bottom: 20px; }}
        </style>
    </head>
    <body>
        <header>
            <div class="logo">Moviee <span>BD</span></div>
            <div class="user-profile">
                <img id="uPic" src="https://cdn-icons-png.flaticon.com/512/3135/3135715.png">
                <span id="uName">Guest</span>
            </div>
        </header>

        <div class="search-section">
            <input type="text" class="search-input" placeholder="মুভি বা এপিসোড সার্চ করুন..." onkeyup="search()">
        </div>

        <div class="movie-grid" id="grid"></div>

        <div id="adScreen" class="ad-overlay">
            <div class="timer" id="timer">10</div>
            <p style="color: #94a3b8;">সার্ভারের সাথে কানেক্ট হচ্ছে...</p>
        </div>

        <script>
            let tg = window.Telegram.WebApp; tg.expand();
            
            if(tg.initDataUnsafe.user) {{
                document.getElementById('uName').innerText = tg.initDataUnsafe.user.first_name;
                if(tg.initDataUnsafe.user.photo_url) document.getElementById('uPic').src = tg.initDataUnsafe.user.photo_url;
            }}

            let movies = [];
            async function load() {{
                const r = await fetch('/api/movies');
                movies = await r.json();
                render(movies);
            }}

            function render(data) {{
                document.getElementById('grid').innerHTML = data.map(m => `
                    <div class="movie-card" onclick="startTimer('\${m._id}')">
                        <img src="\${m.thumbnail}">
                        <div class="movie-info">\${m.title}</div>
                    </div>
                `).join('');
            }}

            function search() {{
                let q = document.querySelector('.search-input').value.toLowerCase();
                render(movies.filter(m => m.title.toLowerCase().includes(q)));
            }}

            function startTimer(id) {{
                document.getElementById('adScreen').style.display = 'flex';
                let t = 10;
                let iv = setInterval(() => {{
                    t--; document.getElementById('timer').innerText = t;
                    if(t <= 0) {{ clearInterval(iv); send(id); }}
                }}, 1000);
            }}

            async function send(id) {{
                await fetch('/api/send', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ userId: tg.initDataUnsafe.user.id, movieId: id }})
                }});
                document.getElementById('adScreen').style.display = 'none';
                tg.close();
            }}
            load();
        </script>
    </body>
    </html>
    """

# --- ৪. API রুটস ---

@app.get("/api/movies")
async def get_movies():
    movies = []
    async for m in db.movies.find().sort("created_at", -1):
        m["_id"] = str(m["_id"])
        movies.append(m)
    return movies

@app.post("/api/send")
async def api_send(data: dict = Body(...)):
    movie = await db.movies.find_one({"_id": ObjectId(data['movieId'])})
    if movie:
        msg = await bot.send_document(data['userId'], movie['file_id'], caption=f"🎬 {movie['title']}\n⚠️ ২৪ ঘণ্টা পর এটি ডিলিট হবে।")
        delete_at = datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        await db.auto_delete.insert_one({"chat_id": data['userId'], "message_id": msg.message_id, "delete_at": delete_at})
    return {"ok": True}

# --- ৫. সার্ভিস রানার ---

async def start():
    scheduler.add_job(delete_expired_files, 'interval', minutes=1)
    scheduler.start()
    port = int(os.getenv("PORT", 8000))
    config = uvicorn.Config(app, host="0.0.0.0", port=port, loop="asyncio")
    server = uvicorn.Server(config)
    await asyncio.gather(server.serve(), dp.start_polling(bot))

if __name__ == "__main__":
    asyncio.run(start())
