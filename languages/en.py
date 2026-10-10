S = {
    "greet_morning": "Good morning 🌞",
    "greet_afternoon": "Good afternoon 🌤",
    "greet_evening": "Good evening 🌆",
    "greet_night": "Good night 🌙",
    "start_txt": (
        "<b>👋 Hey {name}, {greet}!</b>\n\n"
        "<b>🎬 Movies • 📺 Web Series • 🍥 Anime</b>\n"
        "<b>⚡ Fast search • Smart filter</b>\n\n"
        "<b>📝 Just send me a movie name — I'll find it!</b>\n\n"
        "<b>🔔 Latest updates:</b> {updates}\n"
        "<b>✦ Powered by @NeonGhost_Network</b>"
    ),
    "help_txt": (
        "<b>📖 HOW TO USE</b>\n\n"
        "<b>1️⃣ Check the correct name on Google</b>\n"
        "<b>2️⃣ Send that name here or in the group</b>\n"
        "<b>3️⃣ Use these formats:</b>\n\n"
        "<b>🎬 Movie:</b> name + year (e.g. Joker 2019)\n"
        "<b>📺 Series:</b> name + S01 (S01 = season 1)\n"
        "<b>🗣 Language:</b> name + Hindi\n\n"
        "<b>🚀 Follow these steps and get your file!</b>"
    ),
    "about_txt": (
        "<b>🤖 ABOUT ME</b>\n\n"
        "<b>• Name:</b> <a href=\"https://t.me/{bot_user}\">{bot_name}</a>\n"
        "<b>• Developer:</b> <a href=\"{owner}\">Owner</a>\n"
        "<b>• Library:</b> Pyrogram\n"
        "<b>• Language:</b> Python 3\n"
        "<b>• Database:</b> MongoDB\n"
        "<b>• Server:</b> Heroku"
    ),
    "btn_add_group": "➕ Add me to your group",
    "btn_help": "📖 Help",
    "btn_about": "ℹ️ About",
    "btn_top": "🔥 Top searches",
    "btn_premium": "💎 Premium",
    "btn_language": "🌐 Language",
    "btn_admin": "🛠 Admin Panel",
    "btn_back_home": "⬅️ Back to home",
    "btn_close": "❌ Close",
    "lang_saved": "✅ Language saved!",
}

S.update({'limit_reached': '<b>🚫 DAILY LIMIT REACHED</b>\n\n<b>📦 Free users get {limit} files per day.</b>\n\n<b>Choose one to continue 👇</b>\n<b>🔓 Verify</b> — free access for <b>{hours} hours</b>\n<b>💎 Premium</b> — unlimited, no verification', 'btn_verify': '🔓 Verify • Free {hours}h', 'remaining_txt': '<b>📦 Files left today: {left}/{total}</b>', 'del_notice': '<b>⏳ AUTO-DELETE</b>\n<b>This file will be deleted in {time}.</b>\n<b>📥 Download or save it before that.</b>', 'fwd_locked': '<b>🔒 Forwarding is off for free users.</b>\n<b>🔓 Verify or 💎 get Premium to unlock it.</b>', 'deleted_notice': '<b>🗑 File deleted. Search again anytime 😉</b>', 'verify_intro': '<b>🔓 FREE VERIFICATION</b>\n\n<b>1️⃣ Tap “Verify now”</b>\n<b>2️⃣ Complete the page and come back</b>\n<b>3️⃣ Enjoy {hours} hours of unlimited files + forwarding!</b>\n\n<b>❓ Stuck? Tap “How to verify”.</b>', 'btn_verify_now': '✅ Verify now', 'btn_how_to': '🎬 How to verify', 'verify_success': '<b>✅ VERIFIED!</b>\n\n<b>🎉 Unlimited files + forwarding are ON</b>\n<b>⏰ Till {until}</b>', 'btn_get_file': '📥 Get my file', 'verify_fast': '<b>⚠️ Verification failed</b>\n<b>Please open the link, complete the page properly and try again.</b>', 'verify_expired': '<b>⌛ This link has expired. Tap Verify again.</b>', 'verify_unavailable': '<b>🔧 Verification is not available right now.</b>\n<b>💎 Get Premium to continue.</b>', 'verify_active': '<b>✅ You are already verified till {until}.</b>', 'unit_h': 'h', 'unit_m': 'm'})

S.update({'no_file': '<b>❌ File not found. Please search again.</b>'})

S.update({'pl_day': 'Day', 'pl_days': 'Days', 'pl_month': 'Month', 'pl_months': 'Months', 'pl_year': 'Year', 'pl_years': 'Years', 'premium_menu': '<b>💎 GO PREMIUM</b>\n\n<b>✨ What you get:</b>\n<b>♾ Unlimited files, no daily limit</b>\n<b>🔓 No verification, ever</b>\n<b>📤 Forward & save files freely</b>\n<b>📦 Send-all in one tap</b>\n<b>⏳ Files stay longer before auto-delete</b>\n<b>🚫 No force-subscribe</b>\n<b>🚀 Priority for your movie requests</b>\n\n{status}<b>👇 Choose your plan</b>', 'premium_active_line': '<b>✅ Premium active till {until}</b>\n<b>Buying again adds time on top.</b>\n\n', 'no_pay_method': '<b>🔧 Premium payment is not available right now.</b>\n<b>Please contact the owner.</b>', 'btn_contact': '💬 Contact owner', 'btn_back': '⬅️ Back', 'btn_cancel': '🚫 Cancel', 'btn_refer': '🫂 Refer & earn', 'btn_share': '📤 Share my link', 'btn_paid': '✅ I have paid', 'btn_try_again': '🔁 Try again', 'btn_renew': '💎 Renew', 'pay_screen': '<b>💳 PAY ₹{price}</b>\n<b>📦 Plan: {dur}</b>\n\n{methods}\n\n<b>📝 3 EASY STEPS</b>\n<b>1️⃣ Pay exactly ₹{price}</b>\n<b>2️⃣ Take a screenshot of the payment</b>\n<b>3️⃣ Tap “I have paid” and send the screenshot</b>\n\n<b>⏱ Premium starts within minutes after approval.</b>', 'pay_upi_line': '<b>📲 UPI ID:</b> <code>{upi}</code>', 'pay_qr_line': '<b>🖼 Or scan the QR code above</b>', 'send_ss_prompt': '<b>📸 Send your payment screenshot now</b>\n<b>Send it as a photo in this chat 👇</b>', 'ss_received': '<b>✅ Screenshot received!</b>\n<b>⏳ Admin is checking it. You will get a message here once it is approved.</b>', 'ss_pending_exists': '<b>⏳ Your payment is already under review.</b>\n<b>Please wait for the admin.</b>', 'ss_duplicate': '<b>⚠️ This screenshot was already used.</b>\n<b>Please send your own new payment screenshot.</b>', 'ss_need_photo': '<b>📸 Please send the screenshot as a photo.</b>', 'pay_approved': '<b>🎉 PREMIUM ACTIVATED!</b>\n\n<b>📦 Plan: {dur}</b>\n<b>⏰ Valid till {until}</b>\n\n<b>Enjoy unlimited files 🍿</b>', 'pay_rejected': '<b>❌ Payment not verified</b>\n\n<b>We could not find your payment. If you paid, send a clear screenshot again or contact support.</b>', 'remind_exp': '<b>⏰ Your Premium ends in {left}!</b>\n<b>Renew now to keep unlimited access 👇</b>', 'expired_msg': '<b>⌛ Your Premium has ended.</b>\n<b>Renew anytime to get unlimited files again 💎</b>', 'myplan_active': '<b>💎 YOUR PLAN</b>\n\n<b>✅ Premium active</b>\n<b>⏰ Valid till {until}</b>', 'myplan_none': '<b>💎 YOUR PLAN</b>\n\n<b>You are on the Free plan.</b>\n<b>Get Premium for unlimited files 👇</b>', 'refer_menu': '<b>🫂 REFER & EARN</b>\n\n<b>🎁 Invite {need} friends = {days} Premium FREE!</b>\n\n<b>🔗 Your link (tap to copy):</b>\n<code>{link}</code>\n\n<b>👥 Joined: {joined}</b>\n<b>✅ Counted: {qualified}</b>\n<b>📈 Progress: {progress}/{need}</b>\n<b>🏆 Rewards won: {rewards}</b>\n\n<b>ℹ️ A friend counts when he is a new user and gets his first file.</b>', 'refer_off': '<b>🫂 Refer & earn is off right now.</b>', 'refer_share_text': 'Free movies, series & anime on Telegram 🍿 Join with my link!', 'refer_qualified': '<b>🎉 A friend joined and got a file!</b>\n<b>📈 Progress: {progress}/{need}</b>', 'refer_reward': '<b>🏆 REWARD UNLOCKED!</b>\n\n<b>💎 +{days} Premium added</b>\n<b>⏰ Valid till {until}</b>'})

S.update({'start_txt': '<b>🎬 𝗠𝗢𝗩𝗜𝗘 𝗠𝗔𝗦𝗧𝗘𝗥 𝗕𝗢𝗧</b>\n<b>━━━━━━━━━━━━━━━</b>\n\n<b>👋 Hey {name}, {greet}!</b>\n\n<b>🎬 Movies • 📺 Web Series • 🍥 Anime</b>\n<b>⚡ Fast search • Smart filter</b>\n\n<b>📝 Just send me a movie name — I\'ll find it!</b>\n\n<b>━━━━━━━━━━━━━━━</b>\n<b>📢 <a href="{updates}">Latest Updates</a>  •  💬 <a href="{support}">Support</a></b>\n<b>✦ Powered by <a href="{brand}">NeonGhost Network</a></b>', 'about_txt': '<b>🤖 ABOUT ME</b>\n<b>━━━━━━━━━━━━━━━</b>\n\n<b>• Name:</b> <a href="https://t.me/{bot_user}">{bot_name}</a>\n<b>• Made by:</b> <a href="{brand}">NeonGhost Network</a>\n<b>• Support:</b> <a href="{support}">Support</a>\n\n<b>━━━━━━━━━━━━━━━</b>\n💼 This is a paid, private bot.\nWant a bot like this for your own channel?\n👉 Talk to the <a href="{owner}">Owner</a>', 'premium_menu': '<b>💎 GO PREMIUM</b>\n<b>━━━━━━━━━━━━━━━</b>\n\n<b>✨ What you get:</b>\n<b> ➤ ♾️ Unlimited files, no daily limit</b>\n<b> ➤ 🔓 No verification, ever</b>\n<b> ➤ 📤 Forward & save files freely</b>\n<b> ➤ 📦 Send-all in one tap</b>\n<b> ➤ ⏳ Files stay longer before auto-delete</b>\n<b> ➤ 🚫 No force-subscribe</b>\n<b> ➤ 🚀 Priority for your movie requests</b>\n\n<b>━━━━━━━━━━━━━━━</b>\n{status}<b>👇 Choose your plan</b>'})

S.update({'ss_doubt': '<b>❓ Any doubt? Tap below to ask the admin.</b>', 'btn_contact_admin': '💬 Contact admin'})

S.update({'nf_text': '<b>😕 NOT FOUND</b>\n<b>━━━━━━━━━━━━━━━</b>\n\n<b>🔎 {title}</b>\n\n<b>This movie is not in our library yet.</b>\n<b>Tap below and we will add it 👇</b>', 'btn_request': '📩 Request this movie', 'req_sent': '<b>✅ Request sent!</b>\n<b>We will message you here when it is added.</b>', 'req_already': '<b>ℹ️ You already requested this.</b>\n<b>We will message you when it is added.</b>', 'req_expired': '<b>⌛ Please search again and tap Request.</b>', 'req_up': '<b>🎉 GOOD NEWS!</b>\n\n<b>🎬 {title}</b>\n<b>✅ is now added. Tap below to get it 👇</b>', 'req_al': '<b>♻️ {title}</b>\n<b>is already available. Search it again 👇</b>', 'req_un': '<b>⚠️ {title}</b>\n<b>is not available right now. Sorry!</b>', 'req_nr': '<b>📌 {title}</b>\n<b>is not released yet. We will add it after release.</b>', 'req_ws': '<b>♨️ {title}</b>\n<b>Please check the spelling (try Google) and search again.</b>', 'btn_search_now': '🔍 Search now', 'btn_account': '👤 My Account', 'btn_prefs': '⚙️ Preferences', 'btn_downloads': '📥 My Downloads', 'acc_text': '<b>👤 MY ACCOUNT</b>\n<b>━━━━━━━━━━━━━━━</b>\n\n<b>🆔 ID:</b> <code>{uid}</code>\n<b>📦 Plan:</b> {plan}\n<b>📥 Files left today:</b> {left}\n<b>🫂 Referral:</b> {prog}/{need}\n<b>🌐 Language:</b> {lang_name}\n<b>🎞 Preferred:</b> {pref}', 'acc_free': 'Free', 'acc_verified': '✅ Verified till {until}', 'acc_premium': '💎 Premium till {until}', 'acc_unlimited': '♾ Unlimited', 'any_label': 'Any', 'pref_text': '<b>⚙️ PREFERENCES</b>\n<b>━━━━━━━━━━━━━━━</b>\n\n<b>🎞 Quality:</b> {q}\n<b>🗣 Language:</b> {l}\n\n<b>ℹ️ We try your choice first.</b>\n<b>If it is not available, you still get all other files.</b>', 'dl_text': '<b>📥 MY DOWNLOADS</b>\n<b>━━━━━━━━━━━━━━━</b>\n\n<b>Your last files. Tap one to get it again 👇</b>', 'dl_empty': '<b>📥 No downloads yet.</b>\n<b>Search a movie to get started 🍿</b>', 'lang_then_file': '<b>✅ Language saved!</b>\n<b>Tap below to get your file 👇</b>'})
