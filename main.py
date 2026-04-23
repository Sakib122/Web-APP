import os, asyncio, datetime, uvicorn
from fastapi import FastAPI, Body
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from motor.motor_asyncio import AsyncIOMotorClient
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bson import ObjectId

# --- কনফিগারেশন ---
TOKEN = os.getenv("BOT_TOKEN")
MONGO_URL = os.getenv("MONGO_URI")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
APP_URL = os.getenv("APP_URL")

bot = Bot(token=TOKEN)
dp = Dispatcher()
app = FastAPI()

# CORS সেটআপ
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# MongoDB কানেকশন
client = AsyncIOMotorClient(MONGO_URL)
db = client['movie_database']

admin_temp = {}

# --- ১. বটের কাজ (অ্যাডমিন কমান্ড) ---

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    kb = [[types.InlineKeyboardButton(text="🎬 ওপেন মুভি অ্যাপ", web_app=types.WebAppInfo(url=APP_URL))]]
    markup = types.InlineKeyboardMarkup(inline_keyboard=kb)
    
    if message.from_user.id == ADMIN_ID:
        text = (
            "👋 **হ্যালো অ্যাডমিন!**\n\n"
            "⚙️ **কমান্ড প্যানেল:**\n"
            "🔸 অ্যাড আইডি সেট: `/setad [ID]`\n"
            "🔸 টেলিগ্রাম বাটন লিংক: `/settg [URL]`\n"
            "🔸 18+ বাটন লিংক: `/set18 [URL]`\n"
            "🔸 মুভি ডিলিট করতে: `/del`\n\n"
            "📥 **নতুন মুভি অ্যাড করতে প্রথমে ভিডিও বা ডকুমেন্ট ফাইল পাঠান।**"
        )
    else:
        text = f"👋 **স্বাগতম {message.from_user.first_name}!**\nমুভি দেখতে নিচের বাটনে ক্লিক করুন।"
    await message.answer(text, reply_markup=markup, parse_mode="Markdown")

@dp.message(Command("setad"))
async def set_ad(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    try:
        new_id = message.text.split(" ")[1]
        await db.settings.update_one({"id": "ad_config"}, {"$set": {"zone_id": new_id}}, upsert=True)
        await message.answer(f"✅ জোন আইডি আপডেট হয়েছে: `{new_id}`")
    except: await message.answer("ভুল ফরম্যাট! নিয়ম: /setad 10916755")

@dp.message(Command("settg"))
async def set_tg_link(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    try:
        url = message.text.split(" ")[1]
        await db.settings.update_one({"id": "link_tg"}, {"$set": {"url": url}}, upsert=True)
        await message.answer(f"✅ টেলিগ্রাম বাটন লিংক আপডেট হয়েছে: `{url}`")
    except: await message.answer("ভুল ফরম্যাট! নিয়ম: /settg https://t.me/MovieeBD")

@dp.message(Command("set18"))
async def set_18_link(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    try:
        url = message.text.split(" ")[1]
        await db.settings.update_one({"id": "link_18"}, {"$set": {"url": url}}, upsert=True)
        await message.answer(f"✅ 18+ বাটন লিংক আপডেট হয়েছে: `{url}`")
    except: await message.answer("ভুল ফরম্যাট! নিয়ম: /set18 https://t.me/yourlink")

# --- মুভি ডিলিট করার কমান্ড ---
@dp.message(Command("del"))
async def del_movie_list(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    
    movies = []
    # সর্বশেষ আপলোড করা ২০টি মুভি দেখাবে ডিলিট করার জন্য
    async for m in db.movies.find().sort("created_at", -1).limit(20):
        movies.append(m)
    
    if not movies:
        return await message.answer("ডাটাবেসে কোনো মুভি পাওয়া যায়নি।")
        
    builder = InlineKeyboardBuilder()
    for m in movies:
        # বাটনে মুভির নাম থাকবে
        builder.button(text=f"❌ {m['title']}", callback_data=f"del_{str(m['_id'])}")
    
    builder.adjust(1) # প্রতি লাইনে ১টি করে বাটন
    await message.answer("⚠️ **যে মুভিটি ডিলিট করতে চান তার উপর ক্লিক করুন** (সর্বশেষ ২০টি দেখাচ্ছে):", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("del_"))
async def del_movie_callback(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID: return
    
    movie_id = callback.data.split("_")[1]
    try:
        await db.movies.delete_one({"_id": ObjectId(movie_id)})
        await callback.answer("✅ মুভিটি সফলভাবে ডিলিট করা হয়েছে!", show_alert=True)
        await callback.message.delete() # লিস্ট মুছে ফেলবে
    except Exception as e:
        await callback.answer(f"এরর: {e}", show_alert=True)

# --- মুভি আপলোড লজিক ---
@dp.message(F.document | F.video)
async def catch_file(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    if message.video:
        fid = message.video.file_id
        ftype = "video"
    else:
        fid = message.document.file_id
        ftype = "document"
        
    admin_temp[message.from_user.id] = {"file_id": fid, "type": ftype}
    await message.answer("✅ ফাইল পেয়েছি! এখন লিখুন: `নাম | থাম্বনেইল লিঙ্ক`")

@dp.message(F.text)
async def save_movie(message: types.Message):
    if message.from_user.id != ADMIN_ID or "|" not in message.text: return
    uid = message.from_user.id
    if uid not in admin_temp: return
    try:
        title, thumb = message.text.split("|")
        await db.movies.insert_one({
            "title": title.strip(), 
            "thumbnail": thumb.strip(),
            "file_id": admin_temp[uid]["file_id"], 
            "file_type": admin_temp[uid]["type"],
            "created_at": datetime.datetime.utcnow()
        })
        del admin_temp[uid]
        await message.answer("🎉 মুভিটি অ্যাপে যুক্ত করা হয়েছে!")
    except Exception as e: await message.answer(f"এরর: {e}")

# --- ২. ওয়েব অ্যাপ UI ---

@app.get("/", response_class=HTMLResponse)
async def web_ui():
    # ডাটাবেস থেকে লিংক ও জোন আইডি আনা
    ad_cfg = await db.settings.find_one({"id": "ad_config"})
    tg_cfg = await db.settings.find_one({"id": "link_tg"})
    b18_cfg = await db.settings.find_one({"id": "link_18"})
    
    zone_id = ad_cfg['zone_id'] if ad_cfg else "10916755"
    tg_url = tg_cfg['url'] if tg_cfg else "https://t.me/MovieeBD"
    link_18 = b18_cfg['url'] if b18_cfg else "https://t.me/MovieeBD"

    html_code = r"""
    <!DOCTYPE html>
    <html lang="bn">
    <head>
        <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Moviee BD</title>
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
        <style>
            * { margin:0; padding:0; box-sizing:border-box; }
            body { background:#fff; font-family: sans-serif; color:#333; }
            header { display:flex; justify-content:space-between; align-items:center; padding:15px; border-bottom:1px solid #eee; position:sticky; top:0; background:#fff; z-index:1000; }
            .logo { font-size:24px; font-weight:bold; }
            .logo span { background:red; color:#fff; padding:2px 5px; border-radius:5px; margin-left:5px; font-size:16px; }
            .user-info { display:flex; align-items:center; gap:8px; background:#f1f5f9; padding:5px 12px; border-radius:20px; border:1px solid #ddd; font-weight:bold; font-size:14px; }
            .user-info img { width:26px; height:26px; border-radius:50%; border:1px solid #000; object-fit:cover; }
            .search-box { padding:15px; }
            .search-input { width:100%; padding:12px; border-radius:25px; border:2px solid #ddd; outline:none; text-align:center; background:#f9f9f9; transition: border 0.3s; }
            .search-input:focus { border-color: #f87171; }
            .grid { padding:0 15px 100px; }
            .card { margin-bottom:25px; cursor:pointer; }
            .post-content { border-radius:15px; overflow:hidden; border:3px solid; border-image: linear-gradient(to right, #0f0, #00f) 1; position:relative; }
            .post-content img { width:100%; height:200px; object-fit:cover; display:block; }
            .lock-overlay { position:absolute; top:50%; left:50%; transform:translate(-50%, -50%); background:rgba(0,0,0,0.6); padding:5px 15px; border-radius:20px; color:red; font-weight:bold; font-size:12px; display:flex; align-items:center; }
            .card-footer { display:flex; align-items:center; padding:10px 5px; }
            .mb-logo { background:#f87171; color:#fff; width:35px; height:35px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-weight:bold; font-size:14px; margin-right:10px; }
            .floating-18 { position:fixed; bottom:95px; right:20px; background:red; color:white; width:50px; height:50px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-weight:bold; z-index:500; border:2px solid #fff; cursor:pointer; }
            .floating-tg { position:fixed; bottom:30px; right:20px; background:#24A1DE; color:white; width:55px; height:55px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:24px; z-index:500; cursor:pointer; }
            .ad-screen { position:fixed; top:0; left:0; width:100%; height:100%; background:#0f172a; display:none; flex-direction:column; align-items:center; justify-content:center; z-index:2000; color:#fff; }
            .timer { width:100px; height:100px; border-radius:50%; border:5px solid red; display:flex; align-items:center; justify-content:center; font-size:40px; margin-bottom:20px; color:red; font-weight:bold; }
            .modal { position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.8); display:none; align-items:center; justify-content:center; z-index:3000; }
            .modal-content { background:#fff; width:90%; padding:30px; border-radius:15px; text-align:center; color:#333; }
        </style>
    </head>
    <body>
        <header>
            <div class="logo">MovieZone <span>BD</span></div>
            <div class="user-info">
                <span id="uName">Guest</span>
                <img id="uPic" src="https://cdn-icons-png.flaticon.com/512/3135/3135715.png" onerror="this.src='https://cdn-icons-png.flaticon.com/512/3135/3135715.png'">
            </div>
        </header>

        <div class="search-box">
            <input type="text" id="searchInput" class="search-input" placeholder="মুভি বা এপিসোড লাইভ সার্চ করুন...">
        </div>

        <div class="grid" id="movieGrid"><p style="text-align:center; padding:20px; color:gray;">মুভি লোড হচ্ছে...</p></div>

        <!-- ডাইনামিক বাটন লিংক -->
        <div class="floating-18" onclick="window.open('{{LINK_18}}')">18+</div>
        <div class="floating-tg" onclick="window.open('{{TG_LINK}}')"><i class="fa-brands fa-telegram"></i></div>

        <div id="adScreen" class="ad-screen">
            <div class="timer" id="timer">15</div>
            <p>সার্ভারের সাথে কানেক্ট হচ্ছে...</p>
        </div>

        <div id="successModal" class="modal">
            <div class="modal-content">
                <i class="fa-solid fa-circle-check" style="font-size:60px; color:green;"></i>
                <h2 style="margin:15px 0;">সফলভাবে সম্পন্ন হয়েছে!</h2>
                <p style="margin-bottom: 20px; color:gray; font-size: 14px;">বটের ইনবক্স চেক করুন, মুভি পাঠানো হয়েছে।</p>
                <button onclick="tg.close()" style="background:#00ff88; color:#000; padding:12px; border-radius:8px; border:none; width:100%; font-weight:bold; cursor:pointer;">বটে ফিরে যান</button>
            </div>
        </div>

        <script>
            let tg = window.Telegram.WebApp; tg.expand();
            let movies = [];
            const ZONE_ID = "{{ZONE_ID}}";

            // প্রোফাইল সেটআপ
            if(tg.initDataUnsafe && tg.initDataUnsafe.user) {
                document.getElementById('uName').innerText = tg.initDataUnsafe.user.first_name;
                if(tg.initDataUnsafe.user.photo_url) {
                    document.getElementById('uPic').src = tg.initDataUnsafe.user.photo_url;
                }
            }

            // মনিট্যাগ স্ক্রিপ্ট
            const s = document.createElement('script');
            s.src = '//libtl.com/sdk.js'; s.setAttribute('data-zone', ZONE_ID); s.setAttribute('data-sdk', 'show_' + ZONE_ID);
            document.head.appendChild(s);

            // API থেকে ডাটা লোড
            async function load() {
                try {
                    const r = await fetch('/api/list');
                    if (!r.ok) throw new Error("API Error");
                    movies = await r.json();
                    render(movies);
                } catch(e) { 
                    document.getElementById('movieGrid').innerHTML = "<p style='text-align:center;color:red;'>মুভি লোড হতে পারেনি!</p>"; 
                }
            }

            function render(data) {
                const g = document.getElementById('movieGrid');
                if(data.length === 0) { g.innerHTML = "<p style='text-align:center;color:gray;'>কোনো মুভি পাওয়া যায়নি!</p>"; return; }
                g.innerHTML = data.map(m => `
                    <div class="card" onclick="startAd('${m._id}')">
                        <div class="post-content">
                            <img src="${m.thumbnail}" onerror="this.src='https://via.placeholder.com/400x200?text=No+Image'">
                            <div class="lock-overlay"><i class="fa-solid fa-lock"></i> 24H Locked</div>
                        </div>
                        <div class="card-footer">
                            <div class="mb-logo">MB</div>
                            <div style="font-size:14px; font-weight:500;">${m.title}</div>
                        </div>
                    </div>
                `).join('');
            }

            // একদম লাইভ সার্চ লজিক
            document.getElementById('searchInput').addEventListener('input', function(e) {
                let q = e.target.value.toLowerCase().trim();
                if (q === "") {
                    render(movies); // সার্চ ফাঁকা থাকলে সব দেখাবে
                } else {
                    let filtered = movies.filter(m => m.title.toLowerCase().includes(q));
                    render(filtered); // যা মিলবে তা লাইভ দেখাবে
                }
            });

            function startAd(id) {
                if (typeof window['show_' + ZONE_ID] === 'function') window['show_' + ZONE_ID]();
                document.getElementById('adScreen').style.display = 'flex';
                let t = 15;
                let iv = setInterval(() => {
                    t--; document.getElementById('timer').innerText = t;
                    if(t <= 0) { clearInterval(iv); send(id); }
                }, 1000);
            }

            async function send(id) {
                try {
                    await fetch('/api/send', { 
                        method:'POST', 
                        headers:{'Content-Type':'application/json'}, 
                        body:JSON.stringify({userId: tg.initDataUnsafe.user.id, movieId: id})
                    });
                } catch(e) { console.log("Send Error:", e); }
                
                document.getElementById('adScreen').style.display = 'none';
                document.getElementById('successModal').style.display = 'flex';
            }
            
            load();
        </script>
    </body>
    </html>
    """
    
    # ডায়নামিক ভ্যালু রিপ্লেস
    html_code = html_code.replace("{{ZONE_ID}}", zone_id).replace("{{TG_LINK}}", tg_url).replace("{{LINK_18}}", link_18)
    return html_code

# --- ৩. API এবং রানার ---

@app.get("/api/list")
async def list_movies():
    movies = []
    async for m in db.movies.find().sort("created_at", -1):
        m["_id"] = str(m["_id"])
        m["created_at"] = str(m.get("created_at", ""))
        movies.append(m)
    return movies

@app.post("/api/send")
async def send_file(d: dict = Body(...)):
    try:
        m = await db.movies.find_one({"_id": ObjectId(d['movieId'])})
        if m:
            caption_text = f"🎥 {m['title']}\n\nJoin : @MovieeBD"
            
            if m.get("file_type") == "video":
                await bot.send_video(d['userId'], m['file_id'], caption=caption_text)
            else:
                await bot.send_document(d['userId'], m['file_id'], caption=caption_text)
                
    except Exception as e:
        print(f"Error: {e}")
        return {"ok": False}
        
    return {"ok": True}

async def start():
    port = int(os.getenv("PORT", 8000))
    config = uvicorn.Config(app, host="0.0.0.0", port=port, loop="asyncio")
    server = uvicorn.Server(config)
    await bot.delete_webhook(drop_pending_updates=True)
    await asyncio.gather(server.serve(), dp.start_polling(bot))

if __name__ == "__main__":
    asyncio.run(start())
