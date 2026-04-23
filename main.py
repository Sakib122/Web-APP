import os, asyncio, datetime, uvicorn
from fastapi import FastAPI, Body, Request
from fastapi.responses import HTMLResponse
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from motor.motor_asyncio import AsyncIOMotorClient
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bson import ObjectId

# --- Configuration (Environment Variables) ---
TOKEN = os.getenv("BOT_TOKEN")
MONGO_URL = os.getenv("MONGO_URI")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
APP_URL = os.getenv("APP_URL")

bot = Bot(token=TOKEN)
dp = Dispatcher()
app = FastAPI()
scheduler = AsyncIOScheduler()

# --- Database Connection ---
try:
    client = AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=5000)
    db = client['movie_database']
    print("✅ MongoDB Connected Successfully")
except Exception as e:
    print(f"❌ MongoDB Connection Error: {e}")

admin_temp = {}

# --- ১. বটের কাজ (Admin Commands) ---

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    kb = [[types.InlineKeyboardButton(text="🎬 ওপেন মুভি অ্যাপ", web_app=types.WebAppInfo(url=APP_URL))]]
    markup = types.InlineKeyboardMarkup(inline_keyboard=kb)
    
    if message.from_user.id == ADMIN_ID:
        text = (
            "👋 **হ্যালো অ্যাডমিন!**\n\n"
            "🛠 **অ্যাডমিন সেটিংস কমান্ডস:**\n"
            "⚙️ অ্যাড আইডি সেট: `/setad [ID]`\n"
            "🔗 চ্যানেল লিঙ্ক সেট: `/setlink [URL]`\n\n"
            "📥 **মুভি অ্যাড করতে:** প্রথমে মুভি ফাইলটি (Video/Document) এখানে পাঠান।"
        )
    else:
        text = f"👋 **স্বাগতম {message.from_user.first_name}!**\nমুভি দেখতে নিচে ক্লিক করুন।"
    await message.answer(text, reply_markup=markup, parse_mode="Markdown")

@dp.message(Command("setad"))
async def set_ad(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    try:
        new_id = message.text.split(" ")[1]
        await db.settings.update_one({"id": "ad_config"}, {"$set": {"zone_id": new_id}}, upsert=True)
        await message.answer(f"✅ মনিট্যাগ জোন আইডি আপডেট করা হয়েছে: `{new_id}`")
    except:
        await message.answer("⚠️ ভুল ফরম্যাট! লিখুন: `/setad 10916755`")

@dp.message(Command("setlink"))
async def set_link(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    try:
        new_link = message.text.split(" ")[1]
        await db.settings.update_one({"id": "tg_link"}, {"$set": {"url": new_link}}, upsert=True)
        await message.answer(f"✅ টেলিগ্রাম লিঙ্ক আপডেট করা হয়েছে: `{new_link}`")
    except:
        await message.answer("⚠️ ভুল ফরম্যাট! লিখুন: `/setlink https://t.me/MovieeBD`")

@dp.message(F.document | F.video)
async def catch_file(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    fid = message.document.file_id if message.document else message.video.file_id
    admin_temp[message.from_user.id] = fid
    await message.answer("✅ ফাইল পেয়েছি! এখন মুভির নাম ও থাম্বনেইল দিন।\n\n**ফরম্যাট:** `নাম | থাম্বনেইল লিঙ্ক`")

@dp.message(F.text)
async def save_movie(message: types.Message):
    if message.from_user.id != ADMIN_ID or "|" not in message.text: return
    uid = message.from_user.id
    if uid not in admin_temp: return
    
    try:
        title, thumb = message.text.split("|")
        await db.movies.insert_one({
            "title": title.strip(), "thumbnail": thumb.strip(),
            "file_id": admin_temp[uid], "created_at": datetime.datetime.utcnow()
        })
        del admin_temp[uid]
        await message.answer("🎉 মুভিটি সফলভাবে অ্যাপে যুক্ত হয়েছে!")
    except Exception as e:
        await message.answer(f"⚠️ এরর: {e}")

# --- ২. ওয়েব অ্যাপ UI (Premium Matching UI) ---

@app.get("/", response_class=HTMLResponse)
async def web_ui():
    # ডাটাবেস থেকে সেটিংস নেওয়া
    ad_config = await db.settings.find_one({"id": "ad_config"})
    link_config = await db.settings.find_one({"id": "tg_link"})
    
    zone_id = ad_config['zone_id'] if ad_config else "10916755"
    tg_url = link_config['url'] if link_config else "https://t.me/MovieeBD"

    html_code = r"""
    <!DOCTYPE html>
    <html lang="bn">
    <head>
        <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Moviee BD</title>
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
        
        <!-- ডাইনামিক মনিট্যাগ স্ক্রিপ্ট -->
        <script id="adLoader"></script>

        <style>
            * { margin:0; padding:0; box-sizing:border-box; }
            body { background:#fff; font-family: 'Segoe UI', Tahoma, sans-serif; color:#333; }
            
            header { display:flex; justify-content:space-between; align-items:center; padding:12px 18px; border-bottom:1px solid #eee; position:sticky; top:0; background:#fff; z-index:1000; }
            .logo { font-size:22px; font-weight:800; color:#000; }
            .logo span { background:#f00; color:#fff; padding:2px 6px; border-radius:5px; margin-left:4px; font-size:15px; }
            
            .profile-box { display:flex; align-items:center; gap:10px; background:#f1f5f9; padding:5px 15px; border-radius:30px; border:1px solid #e2e8f0; font-weight:600; font-size:13px; }
            .profile-box img { width:28px; height:28px; border-radius:50%; border:1px solid #333; object-fit: cover; }

            .search-section { padding:15px 20px; }
            .search-input { width:100%; padding:14px; border-radius:30px; border:2px solid #e2e8f0; background:#f8fafc; outline:none; text-align:center; font-size:14px; transition: 0.3s; }
            .search-input:focus { border-color: #38bdf8; background:#fff; }

            .grid { padding:0 15px 120px; }
            .card { margin-bottom:25px; cursor:pointer; }
            .thumb-area { border-radius:15px; overflow:hidden; border:3px solid; border-image: linear-gradient(to right, #00ff00, #0000ff) 1; position:relative; box-shadow: 0 4px 15px rgba(0,0,0,0.1); }
            .thumb-area img { width:100%; height:200px; object-fit:cover; display:block; }
            
            .lock-overlay { position:absolute; top:50%; left:50%; transform:translate(-50%, -50%); background:rgba(0,0,0,0.6); padding:6px 15px; border-radius:20px; color:#ff4d4d; font-weight:bold; font-size:12px; display:flex; align-items:center; backdrop-filter: blur(4px); }
            .lock-overlay i { margin-right:6px; }

            .card-footer { display:flex; align-items:center; padding:12px 5px; }
            .mb-circle { background:#ff4d4d; color:#fff; width:38px; height:38px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-weight:900; font-size:14px; margin-right:12px; box-shadow: 0 2px 5px rgba(0,0,0,0.2); }
            .card-info { font-size:14px; color:#334155; font-weight:600; line-height: 1.4; }

            /* Floating Buttons */
            .btn-18 { position:fixed; bottom:95px; right:20px; background:#f00; color:#fff; width:50px; height:50px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-weight:bold; font-size:14px; z-index:999; box-shadow: 0 4px 12px rgba(255,0,0,0.3); border:2px solid #fff; }
            .btn-tg { position:fixed; bottom:30px; right:20px; background:#0088cc; color:#fff; width:55px; height:55px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:25px; z-index:999; box-shadow: 0 4px 15px rgba(0,136,204,0.4); }

            /* Ad Timer */
            .ad-layer { position:fixed; top:0; left:0; width:100%; height:100%; background:#0f172a; display:none; flex-direction:column; align-items:center; justify-content:center; z-index:5000; color:#fff; text-align:center; }
            .timer-ring { width:110px; height:110px; border-radius:50%; border:5px solid #f00; display:flex; align-items:center; justify-content:center; font-size:45px; font-weight:bold; color:#f00; margin-bottom:20px; box-shadow: 0 0 20px rgba(255,0,0,0.3); }

            /* Success Popup */
            .modal-bg { position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.85); display:none; align-items:center; justify-content:center; z-index:6000; padding:20px; }
            .modal-box { background:#fff; width:100%; max-width:350px; padding:35px 25px; border-radius:20px; text-align:center; position:relative; }
            .modal-box i { font-size:65px; color:#22c55e; margin-bottom:20px; }
            .modal-box h2 { font-size:22px; margin-bottom:10px; color:#1e293b; }
            .modal-box p { color:#64748b; font-size:14px; margin-bottom:25px; }
            .btn-close { background:#22c55e; color:#fff; padding:14px; border-radius:12px; border:none; width:100%; font-weight:700; font-size:15px; cursor:pointer; }
        </style>
    </head>
    <body>
        <header>
            <div class="logo">Moviee <span>BD</span></div>
            <div class="profile-box">
                <span id="userName">Admin</span>
                <img id="userPic" src="https://cdn-icons-png.flaticon.com/512/3135/3135715.png">
            </div>
        </header>

        <div class="search-section">
            <input type="text" class="search-input" id="searchInput" placeholder="এপিসোড নাম্বার বা নাম দিয়ে সার্চ করুন..." oninput="liveSearch()">
        </div>

        <div class="grid" id="movieGrid"></div>

        <!-- Floating UI -->
        <div class="btn-18">18+</div>
        <div class="btn-tg" id="tgBtn"><i class="fa-brands fa-telegram"></i></div>

        <!-- Ad Screen -->
        <div id="adArea" class="ad-layer">
            <div class="timer-ring" id="timer">15</div>
            <p style="font-size:18px; font-weight:600;">সার্ভারের সাথে কানেক্ট হচ্ছে...</p>
            <p style="color:#64748b; font-size:13px; margin-top:10px;">অ্যাড শেষ হলে ভিডিও ইনবক্সে যাবে</p>
        </div>

        <!-- Success Modal -->
        <div id="successPop" class="modal-bg">
            <div class="modal-box">
                <i class="fa-solid fa-circle-check"></i>
                <h2>সফলভাবে সম্পন্ন হয়েছে!</h2>
                <p>অ্যাড দেখা সফল হয়েছে! ভিডিওটি পেতে ইনবক্স চেক করুন।</p>
                <button class="btn-close" onclick="tg.close()">ইনবক্স চেক করুন</button>
            </div>
        </div>

        <script>
            let tg = window.Telegram.WebApp; tg.expand();
            let movies = [];
            const ZONE_ID = \"""" + zone_id + r"""\";
            const TG_LINK = \"""" + tg_url + r"""\";

            // ১. প্রোফাইল এবং টেলিগ্রাম বাটন সেটআপ
            if(tg.initDataUnsafe.user) {
                document.getElementById('userName').innerText = tg.initDataUnsafe.user.first_name;
                if(tg.initDataUnsafe.user.photo_url) {
                    document.getElementById('userPic').src = tg.initDataUnsafe.user.photo_url;
                }
            }
            document.getElementById('tgBtn').onclick = () => window.open(TG_LINK);

            // ২. ডাইনামিক মনিট্যাগ স্ক্রিপ্ট
            const adScript = document.createElement('script');
            adScript.src = '//libtl.com/sdk.js';
            adScript.setAttribute('data-zone', ZONE_ID);
            adScript.setAttribute('data-sdk', 'show_' + ZONE_ID);
            document.head.appendChild(adScript);

            // ৩. মুভি লোড এবং রেন্ডার
            async function loadMovies() {
                try {
                    const res = await fetch('/api/list');
                    movies = await res.json();
                    renderGrid(movies);
                } catch(e) { console.error("Database Error"); }
            }

            function renderGrid(data) {
                const grid = document.getElementById('movieGrid');
                if(data.length === 0) {
                    grid.innerHTML = "<p style='text-align:center; padding:20px;'>কোন মুভি পাওয়া যায়নি!</p>";
                    return;
                }
                grid.innerHTML = data.map(m => `
                    <div class="card" onclick="openAd('${m._id}')">
                        <div class="thumb-area">
                            <img src="${m.thumbnail}" onerror="this.src='https://via.placeholder.com/400x200?text=No+Image'">
                            <div class="lock-overlay"><i class="fa-solid fa-lock"></i> 24H Locked</div>
                        </div>
                        <div class="card-footer">
                            <div class="mb-circle">MB</div>
                            <div class="card-info">${m.title} <br><span style="color:#94a3b8; font-size:12px;">Join : @MovieeBD</span></div>
                        </div>
                    </div>
                `).join('');
            }

            // ৪. লাইভ সার্চ ফাংশন
            function liveSearch() {
                const query = document.getElementById('searchInput').value.toLowerCase();
                const filtered = movies.filter(m => m.title.toLowerCase().includes(query));
                renderGrid(filtered);
            }

            // ৫. অ্যাড এবং সেন্ড প্রসেস
            function openAd(id) {
                if (typeof window['show_' + ZONE_ID] === 'function') {
                    window['show_' + ZONE_ID]();
                }
                document.getElementById('adArea').style.display = 'flex';
                let timeLeft = 15;
                const timerInt = setInterval(() => {
                    timeLeft--;
                    document.getElementById('timer').innerText = timeLeft;
                    if(timeLeft <= 0) {
                        clearInterval(timerInt);
                        finishRequest(id);
                    }
                }, 1000);
            }

            async function finishRequest(id) {
                await fetch('/api/send', {
                    method: 'POST',
                    headers: {'Content-Type':'application/json'},
                    body: JSON.stringify({ userId: tg.initDataUnsafe.user.id, movieId: id })
                });
                document.getElementById('adArea').style.display = 'none';
                document.getElementById('successPop').style.display = 'flex';
            }

            loadMovies();
        </script>
    </body>
    </html>
    """
    return html_code

# --- ৩. API এবং সার্ভিস রানার ---

@app.get("/api/list")
async def get_all_movies():
    movies = []
    try:
        async for m in db.movies.find().sort("created_at", -1):
            m["_id"] = str(m["_id"])
            movies.append(m)
    except Exception as e:
        print(f"Fetch Error: {e}")
    return movies

@app.post("/api/send")
async def send_to_inbox(data: dict = Body(...)):
    movie = await db.movies.find_one({"_id": ObjectId(data['movieId'])})
    if movie:
        await bot.send_document(data['userId'], movie['file_id'], caption=f"🎥 {movie['title']}\n\nJoin : @MovieeBD")
    return {"ok": True}

async def start_server():
    port = int(os.getenv("PORT", 8000))
    config = uvicorn.Config(app, host="0.0.0.0", port=port, loop="asyncio")
    server = uvicorn.Server(config)
    await bot.delete_webhook(drop_pending_updates=True)
    await asyncio.gather(server.serve(), dp.start_polling(bot))

if __name__ == "__main__":
    asyncio.run(start_server())
