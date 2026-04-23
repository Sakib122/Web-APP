import os
import asyncio
import datetime
from fastapi import FastAPI, Request, Body
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
client = AsyncIOMotorClient(MONGO_URL)
db = client['movie_database']
scheduler = AsyncIOScheduler()

# --- ১. বটের কাজ (ইউজার গাইড এবং ফাইল সেভিং) ---

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    # স্টার্ট কমান্ডে বিস্তারিত গাইড
    guide_text = (
        f"👋 হ্যালো {message.from_user.full_name}!\n\n"
        "🎬 **আমাদের মুভি বটে আপনাকে স্বাগতম।**\n\n"
        "এখানে মুভি বা সিরিজ পাওয়ার নিয়মাবলী:\n"
        "১️⃣ নিচে দেওয়া **'ওপেন মুভি অ্যাপ'** বাটনে ক্লিক করুন।\n"
        "২️⃣ অ্যাপের ভেতরে আপনার পছন্দের মুভিটি সার্চ করুন।\n"
        "৩️⃣ মুভির পোস্টারের উপরে ক্লিক করুন।\n"
        "৪️⃣ ১০ সেকেন্ড অপেক্ষা করুন (সার্ভারের সাথে কানেক্ট হওয়ার জন্য)।\n"
        "৫️⃣ এরপর অটোমেটিক আপনার ইনবক্সে মুভিটি চলে আসবে।\n\n"
        "⚠️ **সতর্কতা:** ইনবক্সে আসা মুভিটি ২৪ ঘণ্টা পর অটো ডিলিট হয়ে যাবে, তাই দ্রুত ডাউনলোড করে নিন।"
    )
    
    kb = [[types.InlineKeyboardButton(text="🎬 ওপেন মুভি অ্যাপ", web_app=types.WebAppInfo(url=APP_URL))]]
    markup = types.InlineKeyboardMarkup(inline_keyboard=kb)
    
    await message.answer(guide_text, reply_markup=markup, parse_mode="Markdown")

@dp.message(F.document)
async def handle_admin_upload(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    
    try:
        # ফরম্যাট: Title | ImageURL
        title, thumb = message.caption.split("|")
        movie_data = {{
            "title": title.strip(),
            "thumbnail": thumb.strip(),
            "file_id": message.document.file_id,
            "created_at": datetime.datetime.utcnow()
        }}
        await db.movies.insert_one(movie_data)
        await message.answer("✅ অভিনন্দন অ্যাডমিন! ফাইলটি অ্যাপে লাইভ করা হয়েছে।")
    except:
        await message.answer("❌ ফরম্যাট ভুল! ক্যাপশনে লিখুন: মুভির নাম | ইমেজ লিঙ্ক")

# --- ২. অটো ডিলিট লজিক (২৪ ঘণ্টা পর) ---
async def auto_delete_task():
    now = datetime.datetime.utcnow()
    expired = db.auto_delete.find({{"delete_at": {{"$lte": now}}}})
    async for item in expired:
        try:
            await bot.delete_message(item['chat_id'], item['message_id'])
        except: pass
        await db.auto_delete.delete_one({{"_id": item['_id']}})

# --- ৩. ওয়েব অ্যাপ (ফ্রন্টএন্ড ডিজাইন) ---

@app.get("/", response_class=HTMLResponse)
async def web_app_ui():
    return f"""
    <!DOCTYPE html>
    <html lang="bn">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Moviee BD App</title>
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ background: #080a12; color: white; font-family: 'Segoe UI', Tahoma, sans-serif; }}
            
            header {{ display: flex; justify-content: space-between; align-items: center; padding: 15px 20px; background: rgba(13, 17, 23, 0.9); backdrop-filter: blur(10px); position: sticky; top: 0; z-index: 1000; border-bottom: 1px solid #1e293b; }}
            .logo {{ font-size: 22px; font-weight: bold; }}
            .logo span {{ background: #e11d48; padding: 2px 6px; border-radius: 4px; font-size: 14px; margin-left: 5px; }}
            
            .user-info {{ display: flex; align-items: center; gap: 8px; background: #1e293b; padding: 4px 10px; border-radius: 20px; border: 1px solid #334155; }}
            .user-info img {{ width: 25px; height: 25px; border-radius: 50%; border: 2px solid #38bdf8; }}
            .user-info span {{ font-size: 12px; }}

            .search-box {{ padding: 20px; }}
            .search-bar {{ width: 100%; padding: 14px; border-radius: 12px; border: 1px solid #334155; background: #111827; color: white; outline: none; font-size: 15px; }}
            .search-bar:focus {{ border-color: #38bdf8; box-shadow: 0 0 10px rgba(56, 189, 248, 0.2); }}

            .movie-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; padding: 0 20px 20px; }}
            .movie-card {{ background: #111827; border-radius: 12px; overflow: hidden; position: relative; aspect-ratio: 2/3; border: 1px solid #1f2937; box-shadow: 0 8px 16px rgba(0,0,0,0.4); }}
            .movie-card img {{ width: 100%; height: 100%; object-fit: cover; }}
            .movie-title {{ position: absolute; bottom: 0; width: 100%; background: linear-gradient(transparent, rgba(0,0,0,0.9)); padding: 15px 5px 8px; text-align: center; font-size: 13px; font-weight: 500; }}

            /* Ad Timer Overlay */
            .ad-screen {{ position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: #000; display: none; flex-direction: column; align-items: center; justify-content: center; z-index: 10000; }}
            .timer-circle {{ width: 100px; height: 100px; border-radius: 50%; border: 4px solid #e11d48; display: flex; align-items: center; justify-content: center; font-size: 40px; font-weight: bold; color: #e11d48; margin-bottom: 20px; }}
            .status-text {{ color: #94a3b8; font-size: 16px; }}
        </style>
    </head>
    <body>
        <header>
            <div class="logo">Moviee <span>BD</span></div>
            <div class="user-info">
                <img id="uPic" src="https://via.placeholder.com/50">
                <span id="uName">Guest</span>
            </div>
        </header>

        <div class="search-box">
            <input type="text" class="search-bar" placeholder="এপিসোড নাম্বার বা নাম দিয়ে সার্চ করুন..." onkeyup="searchMovies()">
        </div>

        <div class="movie-grid" id="grid"></div>

        <div id="adScreen" class="ad-screen">
            <div class="timer-circle" id="timer">10</div>
            <p class="status-text">সার্ভারের সাথে কানেক্ট হচ্ছে...</p>
        </div>

        <script>
            const tg = window.Telegram.WebApp;
            tg.expand();
            
            if(tg.initDataUnsafe.user) {{
                document.getElementById('uName').innerText = tg.initDataUnsafe.user.first_name;
                if(tg.initDataUnsafe.user.photo_url) {{
                    document.getElementById('uPic').src = tg.initDataUnsafe.user.photo_url;
                }}
            }}

            let allMovies = [];
            async function fetchMovies() {{
                const res = await fetch('/api/movies');
                allMovies = await res.json();
                render(allMovies);
            }}

            function render(data) {{
                const grid = document.getElementById('grid');
                grid.innerHTML = data.map(m => `
                    <div class="movie-card" onclick="startTimer('\${m._id}')">
                        <img src="\${m.thumbnail}">
                        <div class="movie-title">\${m.title}</div>
                    </div>
                `).join('');
            }}

            function searchMovies() {{
                const q = document.querySelector('.search-bar').value.toLowerCase();
                render(allMovies.filter(m => m.title.toLowerCase().includes(q)));
            }}

            function startTimer(id) {{
                document.getElementById('adScreen').style.display = 'flex';
                let timeLeft = 10;
                const interval = setInterval(() => {{
                    timeLeft--;
                    document.getElementById('timer').innerText = timeLeft;
                    if(timeLeft <= 0) {{
                        clearInterval(interval);
                        sendToInbox(id);
                    }}
                }}, 1000);
            }}

            async function sendToInbox(movieId) {{
                await fetch('/api/send-file', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ userId: tg.initDataUnsafe.user.id, movieId: movieId }})
                }});
                document.getElementById('adScreen').style.display = 'none';
                tg.close();
            }}

            fetchMovies();
        </script>
    </body>
    </html>
    """

# --- ৪. API এবং ব্যাকএন্ড লজিক ---

@app.get("/api/movies")
async def api_get_movies():
    movies = []
    async for m in db.movies.find().sort("created_at", -1):
        m["_id"] = str(m["_id"])
        movies.append(m)
    return movies

@app.post("/api/send-file")
async def api_send_file(payload: dict = Body(...)):
    movie = await db.movies.find_one({{"_id": ObjectId(payload['movieId'])}})
    if movie:
        # ফাইল ইনবক্সে পাঠানো
        msg = await bot.send_document(
            payload['userId'], 
            movie['file_id'], 
            caption=f"🎬 মুভির নাম: {movie['title']}\n\n⚠️ এটি ২৪ ঘণ্টা পর আপনার ইনবক্স থেকে মুছে যাবে।"
        )
        # ডিলিট টাইম সেভ করা
        delete_at = datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        await db.auto_delete.insert_one({{
            "chat_id": payload['userId'], 
            "message_id": msg.message_id, 
            "delete_at": delete_at
        }})
    return {{"status": "ok"}}

# --- ৫. সার্ভিস রানার (Koyeb/Render এর জন্য) ---

async def main():
    # অটো ডিলিট টাস্ক চালু করা
    scheduler.add_job(auto_delete_task, 'interval', minutes=1)
    scheduler.start()
    
    # পোর্ট কনফিগারেশন
    port = int(os.getenv("PORT", 8000))
    config = uvicorn.Config(app, host="0.0.0.0", port=port, loop="asyncio")
    server = uvicorn.Server(config)
    
    # বট এবং ওয়েব সার্ভার একসাথে চালানো
    await asyncio.gather(server.serve(), dp.start_polling(bot))

if __name__ == "__main__":
    asyncio.run(main())
