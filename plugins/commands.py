import os
import re, sys
import json
import base64
import logging
import random
import asyncio
import time
import string
import pytz
from .pmfilter import auto_filter 
from Script import script
from datetime import datetime, timedelta
from database.refer import referdb
from database.config_db import mdb
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, ReplyKeyboardMarkup
from pyrogram import Client, filters, enums, StopPropagation
from pyrogram.errors import FloodWait, ChatAdminRequired, UserNotParticipant
from database.ia_filterdb import Media, Media2, MEDIA_DBS, delete_file_by_id, delete_files_by_query, get_file_details, unpack_new_file_id, get_bad_files, get_cover_url, backfill_media_type
from database.users_chats_db import db
from info import *
from utils import get_settings, save_group_settings, is_subscribed, is_req_subscribed, get_size, is_check_admin, temp, get_readable_time, get_time, generate_settings_text, log_error, clean_filename, extract_caption_meta, enforce_daily_limit, build_file_caption, get_protect_content, brand_clean



logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

TIMEZONE = "Asia/Kolkata"
BATCH_FILES = {}

@Client.on_message(filters.command("start") & filters.incoming)
async def start(client, message):
    if EMOJI_MODE:
        try:
            await message.react(emoji=random.choice(REACTIONS), big=True)
        except Exception:
            await message.react(emoji="⚡️", big=True)
    m = message
    if message.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        buttons = [[
                    InlineKeyboardButton('❤️ ᴀᴅᴅ ᴍᴇ ᴛᴏ ʏᴏᴜʀ ɢʀᴏᴜᴘ ❤️', url=f'http://t.me/{temp.U_NAME}?startgroup=true')
                ],[
                    InlineKeyboardButton('🍁 ᴊᴏɪɴ ᴜᴘᴅᴀᴛᴇꜱ ᴄʜᴀɴɴᴇʟ 🍁', url=UPDATE_CHNL_LNK)
                  ]]
        reply_markup = InlineKeyboardMarkup(buttons)
        await message.reply(script.GSTART_TXT.format(message.from_user.mention if message.from_user else message.chat.title, temp.U_NAME, temp.B_NAME), reply_markup=reply_markup, disable_web_page_preview=True)
        await asyncio.sleep(2) 
        if not await db.get_chat(message.chat.id):
            total=await client.get_chat_members_count(message.chat.id)
            await client.send_message(LOG_CHANNEL, script.LOG_TEXT_G.format(message.chat.title, message.chat.id, total, "Unknown"))       
            await db.add_chat(message.chat.id, message.chat.title)
        return 
    if not await db.is_user_exist(message.from_user.id):
        await db.add_user(message.from_user.id, message.from_user.first_name)
        await client.send_message(LOG_CHANNEL, script.LOG_TEXT_P.format(message.from_user.id, message.from_user.mention))
    if len(message.command) != 2:
        buttons = [[
                    InlineKeyboardButton('🔰 ᴀᴅᴅ ᴍᴇ ᴛᴏ ʏᴏᴜʀ ɢʀᴏᴜᴘ 🔰', url=f'http://telegram.me/{temp.U_NAME}?startgroup=true')
                ],[
                    InlineKeyboardButton('• ʜᴇʟᴘ 📢', callback_data='help'),
                    InlineKeyboardButton('• ᴀʙᴏᴜᴛ 📖 •', callback_data='about')
                ],[
                    InlineKeyboardButton('⭐ ᴛᴏᴘ sᴇᴀʀᴄʜɪɴɢ ⭐', callback_data="topsearch"),
                    InlineKeyboardButton('• ᴜᴘɢʀᴀᴅᴇ ᴀᴄᴄᴏᴜɴᴛ 🎟', callback_data="premium_info"),
                ]]
        reply_markup = InlineKeyboardMarkup(buttons)
        current_time = datetime.now(pytz.timezone(TIMEZONE))
        curr_time = current_time.hour        
        if curr_time < 12:
            gtxt = "ɢᴏᴏᴅ ᴍᴏʀɴɪɴɢ 🌞" 
        elif curr_time < 17:
            gtxt = "ɢᴏᴏᴅ ᴀғᴛᴇʀɴᴏᴏɴ 🌓" 
        elif curr_time < 21:
            gtxt = "ɢᴏᴏᴅ ᴇᴠᴇɴɪɴɢ 🌘"
        else:
            gtxt = "ɢᴏᴏᴅ ɴɪɢʜᴛ 🌑"
        m=await message.reply_text("⏳")
        await asyncio.sleep(0.4)
        await m.delete()        
        await message.reply_photo(
            photo=random.choice(PICS),
            caption=script.START_TXT.format(message.from_user.mention, gtxt, temp.U_NAME, temp.B_NAME),
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML
        )
        return

    if len(message.command) == 2 and message.command[1] in ["subscribe", "error", "okay", "help"]:
        buttons = [[
                    InlineKeyboardButton('🔰 ᴀᴅᴅ ᴍᴇ ᴛᴏ ʏᴏᴜʀ ɢʀᴏᴜᴘ 🔰', url=f'http://telegram.me/{temp.U_NAME}?startgroup=true')
                ],[
                    InlineKeyboardButton('• ʜᴇʟᴘ 📢 •', callback_data='help'),
                    InlineKeyboardButton('• ᴀʙᴏᴜᴛ 📖 •', callback_data='about')
                ],[
                    InlineKeyboardButton('⭐ ᴛᴏᴘ sᴇᴀʀᴄʜɪɴɢ ⭐', callback_data="topsearch"),
                    InlineKeyboardButton('• ᴜᴘɢʀᴀᴅᴇ ᴀᴄᴄᴏᴜɴᴛ 🎟', callback_data="premium_info"),
                ]]
        reply_markup = InlineKeyboardMarkup(buttons)
        current_time = datetime.now(pytz.timezone(TIMEZONE))
        curr_time = current_time.hour        
        if curr_time < 12:
            gtxt = "ɢᴏᴏᴅ ᴍᴏʀɴɪɴɢ 🌞" 
        elif curr_time < 17:
            gtxt = "ɢᴏᴏᴅ ᴀғᴛᴇʀɴᴏᴏɴ 🌓" 
        elif curr_time < 21:
            gtxt = "ɢᴏᴏᴅ ᴇᴠᴇɴɪɴɢ 🌘"
        else:
            gtxt = "ɢᴏᴏᴅ ɴɪɢʜᴛ 🌑"
        m=await message.reply_text("⏳")
        await asyncio.sleep(0.4)
        await m.delete()        
        await message.reply_photo(
            photo=random.choice(PICS),
            caption=script.START_TXT.format(message.from_user.mention, gtxt, temp.U_NAME, temp.B_NAME),
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML
        )
        return
    if message.command[1].startswith("reff_"):
        try:
            user_id = int(message.command[1].split("_")[1])
        except ValueError:
            await message.reply_text("Invalid refer!")
            return
        if user_id == message.from_user.id:
            await message.reply_text("Hᴇʏ Dᴜᴅᴇ, Yᴏᴜ Cᴀɴ'ᴛ Rᴇғᴇʀ Yᴏᴜʀsᴇʟғ 🤣!\n\nsʜᴀʀᴇ ʟɪɴᴋ ʏᴏᴜʀ ғʀɪᴇɴᴅ ᴀɴᴅ ɢᴇᴛ 10 ʀᴇғᴇʀʀᴀʟ ᴘᴏɪɴᴛ ɪғ ʏᴏᴜ ᴀʀᴇ ᴄᴏʟʟᴇᴄᴛɪɴɢ 100 ʀᴇғᴇʀʀᴀʟ ᴘᴏɪɴᴛs ᴛʜᴇɴ ʏᴏᴜ ᴄᴀɴ ɢᴇᴛ 1 ᴍᴏɴᴛʜ ғʀᴇᴇ ᴘʀᴇᴍɪᴜᴍ ᴍᴇᴍʙᴇʀsʜɪᴘ.")
            return
        if await referdb.is_user_in_list(message.from_user.id):
            await message.reply_text("Yᴏᴜ ʜᴀᴠᴇ ʙᴇᴇɴ ᴀʟʀᴇᴀᴅʏ ɪɴᴠɪᴛᴇᴅ ❗")
            return
        if await db.is_user_exist(message.from_user.id): 
            await message.reply_text("‼️ Yᴏᴜ Hᴀᴠᴇ Bᴇᴇɴ Aʟʀᴇᴀᴅʏ Iɴᴠɪᴛᴇᴅ ᴏʀ Jᴏɪɴᴇᴅ")
            return 
        try:
            uss = await client.get_users(user_id)
        except Exception:
            return             
        await referdb.add_user(message.from_user.id)
        fromuse = await referdb.get_refer_points(user_id) + 10
        if fromuse == 100:
            await referdb.add_refer_points(user_id, 0) 
            await message.reply_text(f"🎉 𝗖𝗼𝗻𝗴𝗿𝗮𝘁𝘂𝗹𝗮𝘁𝗶𝗼𝗻𝘀! 𝗬𝗼𝘂 𝘄𝗼𝗻 𝟭𝟬 𝗥𝗲𝗳𝗲𝗿𝗿𝗮𝗹 𝗽𝗼𝗶𝗻𝘁 𝗯𝗲𝗰𝗮𝘂𝘀𝗲 𝗬𝗼𝘂 𝗵𝗮𝘃𝗲 𝗯𝗲𝗲𝗻 𝗦𝘂𝗰𝗰𝗲𝘀𝘀𝗳𝘂𝗹𝗹𝘆 𝗜𝗻𝘃𝗶𝘁𝗲𝗱 ☞ {uss.mention}!")                    
            await message.reply_text(user_id, f"You have been successfully invited by {message.from_user.mention}!")         
            seconds = 2592000
            if seconds > 0:
                expiry_time = datetime.now(pytz.utc) + timedelta(seconds=seconds)
                user_data = {"id": user_id, "expiry_time": expiry_time}  # Using "id" instead of "user_id"  
                await db.update_user(user_data)  # Use the update_user method to update or insert user data                    
                await client.send_message(
                chat_id=user_id,
                text=f"<b>Hᴇʏ {uss.mention}\n\nYᴏᴜ ɢᴏᴛ 1 ᴍᴏɴᴛʜ ᴘʀᴇᴍɪᴜᴍ sᴜʙsᴄʀɪᴘᴛɪᴏɴ ʙʏ ɪɴᴠɪᴛɪɴɢ 10 ᴜsᴇʀs ❗", disable_web_page_preview=True              
                )
            for admin in ADMINS:
                await client.send_message(chat_id=admin, text=f"Sᴜᴄᴄᴇss ғᴜʟʟʏ ᴛᴀsᴋ ᴄᴏᴍᴘʟᴇᴛᴇᴅ ʙʏ ᴛʜɪs ᴜsᴇʀ:\n\nuser Nᴀᴍᴇ: {uss.mention}\n\nUsᴇʀ ɪᴅ: {uss.id}!")        
        else:
            await referdb.add_refer_points(user_id, fromuse)
            await message.reply_text(f"You have been successfully invited by {uss.mention}!")
            await client.send_message(user_id, f"𝗖𝗼𝗻𝗴𝗿𝗮𝘁𝘂𝗹𝗮𝘁𝗶𝗼𝗻𝘀! 𝗬𝗼𝘂 𝘄𝗼𝗻 𝟭𝟬 𝗥𝗲𝗳𝗲𝗿𝗿𝗮𝗹 𝗽𝗼𝗶𝗻𝘁 𝗯𝗲𝗰𝗮𝘂𝘀𝗲 𝗬𝗼𝘂 𝗵𝗮𝘃𝗲 𝗯𝗲𝗲𝗻 𝗦𝘂𝗰𝗰𝗲𝘀𝘀𝗳𝘂𝗹𝗹𝘆 𝗜𝗻𝘃𝗶𝘁𝗲𝗱 ☞{message.from_user.mention}!")
        return

    if len(message.command) == 2 and message.command[1] in ["premium"]:
        buttons = [[
                    InlineKeyboardButton('📲 ꜱᴇɴᴅ ᴘᴀʏᴍᴇɴᴛ ꜱᴄʀᴇᴇɴꜱʜᴏᴛ 📲', url=OWNER_LNK)
                  ],[
                    InlineKeyboardButton('❌ ᴄʟᴏꜱᴇ ❌', callback_data='close_data')
                  ]]
        reply_markup = InlineKeyboardMarkup(buttons)
        await message.reply_photo(
            photo=(SUBSCRIPTION),
            caption=script.PREPLANS_TXT.format(message.from_user.mention, OWNER_UPI_ID, QR_CODE),
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML
        )
        return  

    if len(message.command) == 2 and message.command[1].startswith('getfile'):
        movies = message.command[1].split("-", 1)[1] 
        movie = movies.replace('-',' ')
        message.text = movie 
        await auto_filter(client, message) 
        raise StopPropagation

    data = message.command[1]
    try:
        _, grp_id, file_id = data.split("_", 2)
        grp_id = int(grp_id)
    except Exception:
        grp_id = 0
        file_id = data

    # Fetch file details concurrently with user checks
    file_details_task = asyncio.create_task(get_file_details(file_id))

    if not await db.has_premium_access(message.from_user.id): 
        try:
            btn = []
            chat = grp_id
            settings      = await get_settings(chat)
            fsub_channels = list(dict.fromkeys((settings.get('fsub', []) if settings else [])+ AUTH_CHANNELS)) 

            if fsub_channels:
                btn += await is_subscribed(client, message.from_user.id, fsub_channels)
            if AUTH_REQ_CHANNELS:
                btn += await is_req_subscribed(client, message.from_user.id, AUTH_REQ_CHANNELS)
            if btn:
                if len(message.command) > 1 and "_" in message.command[1]:
                    kk, file_id = message.command[1].split("_", 1)
                    btn.append([
                        InlineKeyboardButton("♻️ ᴛʀʏ ᴀɢᴀɪɴ ♻️", callback_data=f"checksub#{kk}#{file_id}")
                    ])
                    reply_markup = InlineKeyboardMarkup(btn)
                photo = random.choice(FSUB_PICS) if FSUB_PICS else "https://i.ibb.co/cXrcfZPN/photo-2026-04-20-04-40-07-7630696664830836752.jpg"
                caption = (
                    f"👋 ʜᴇʟʟᴏ {message.from_user.mention}\n\n"
                    "❣️ ʏᴏᴜ ᴍᴜsᴛ ᴊᴏɪɴ ᴛʜᴇ ʀᴇǫᴜɪʀᴇᴅ ᴄʜᴀɴɴᴇʟs ᴛᴏ ᴄᴏɴᴛɪɴᴜᴇ.\n"
                    "👉 ᴊᴏɪɴ ᴀʟʟ ᴛʜᴇ ʙᴇʟᴏᴡ ᴄʜᴀɴɴᴇʟs ᴀɴᴅ ᴛʀʏ ᴀɢᴀɪɴ.\n"
                    "⚠️पहले ʙᴀᴄᴋᴜᴘ ᴄʜᴀɴɴᴇʟ ज्वॉइन करो फिर वापस 🔙 आ कर ᴛʀʏ ᴀɢᴀɪɴ पर क्लिक करें।"
                )
                await message.reply_photo(
                    photo=photo,
                    caption=caption,
                    reply_markup=reply_markup,
                    parse_mode=enums.ParseMode.HTML
                )
                return

        except Exception as e:
            await log_error(client, f"❗️ Force Sub Error:\n\n{repr(e)}")
            logger.error(f"❗️ Force Sub Error:\n\n{repr(e)}")


    user_id = m.from_user.id

    if data.startswith("allfiles"):
        try:
            files = temp.GETALL.get(file_id)
            if not files:
                return await message.reply('<b><i>ɴᴏ ꜱᴜᴄʜ ꜰɪʟᴇ ᴇxɪꜱᴛꜱ !</b></i>')

            # --- Daily Download Limit System: check BEFORE the batch starts sending ---
            dl_status = await db.get_download_status(message.from_user.id)
            is_premium_user = dl_status["is_premium"]
            if is_premium_user:
                files_to_send = files
            else:
                if dl_status["remaining"] <= 0:
                    # Limit already used up -> send the 🚫 message + buttons and stop, no files sent
                    await enforce_daily_limit(client, message)
                    return
                # Show remaining limit BEFORE the files are sent
                await client.send_message(
                    chat_id=message.from_user.id,
                    text=script.REMAINING_LIMIT_TXT.format(dl_status["remaining"], DAILY_DOWNLOAD_LIMIT),
                    parse_mode=enums.ParseMode.HTML
                )
                # Only send as many files as the free user still has remaining today
                files_to_send = files[:dl_status["remaining"]]

            filesarr = []
            for file in files_to_send:
                f_id = file.file_id
                # Caption ALWAYS from Script.py (old DB files too); old channel names replaced.
                f_caption = build_file_caption(file.file_name, file.file_size, file.caption)
                btn = [[InlineKeyboardButton('📌 ᴊᴏɪɴ ᴜᴘᴅᴀᴛᴇꜱ ᴄʜᴀɴɴᴇʟ 📌', url=UPDATE_CHNL_LNK)]]
                cover_url = getattr(file, 'cover', None) if COVERX else None

                # FloodWait fix: retry up to 3 times if Telegram asks us to slow down,
                # instead of letting the whole batch crash out on the first FloodWait.
                msg = None
                for attempt in range(3):
                    try:
                        msg = await client.send_cached_media(
                            chat_id=message.from_user.id,
                            file_id=f_id,
                            caption=f_caption,
                            protect_content=get_protect_content(),
                            reply_markup=InlineKeyboardMarkup(btn),
                            cover=cover_url
                        )
                        break
                    except FloodWait as e:
                        await asyncio.sleep(e.value + 1)

                if msg is not None:
                    filesarr.append(msg)
                await asyncio.sleep(0.3) # यहाँ लूप खत्म हो रहा है

            # --- Daily Download Limit System: bulk-increment by files actually sent (free users only) ---
            if not is_premium_user and filesarr:
                await db.increase_download(message.from_user.id, len(filesarr))

            # If the batch got truncated due to the limit, tell the user now (0 remaining at this point)
            if not is_premium_user and len(files_to_send) < len(files):
                await enforce_daily_limit(client, message)

            # --- अब ये लाइनें FOR LOOP के बाहर हैं (4 स्पेस पीछे) ---
            if filesarr:
                k = await client.send_message(chat_id=message.from_user.id, text=script.DEL_MSG.format(get_time(DELETE_TIME)), parse_mode=enums.ParseMode.HTML)
                await asyncio.sleep(DELETE_TIME)
                for x in filesarr:
                    try: await x.delete()
                    except: pass
                await k.edit_text("<b>ʏᴏᴜʀ ᴀʟʟ ᴠɪᴅᴇᴏꜱ/ꜰɪʟᴇꜱ ᴀʀᴇ ᴅᴇʟᴇᴛᴇᴅ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ !!\nᴋɪɴᴅʟʏ ꜱᴇᴀʀᴄʜ ᴀɢᴀɪɴ 😉</b>")

            return # फंक्शन यहाँ खत्म होगा

        except Exception as e:
            logger.exception(e)
            return


    user = message.from_user.id
    files_ = await file_details_task
    settings = await get_settings(int(grp_id))
    if not files_:
        pre, file_id = ((base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))).decode("utf-8")).split("_", 1)
        # --- Daily Download Limit System: check before sending the file ---
        allowed, is_premium_user, remaining = await enforce_daily_limit(client, message)
        if not allowed:
            return
        # Show remaining limit BEFORE the file is sent
        if not is_premium_user:
            await message.reply_text(
                script.REMAINING_LIMIT_TXT.format(max(remaining - 1, 0), DAILY_DOWNLOAD_LIMIT),
                parse_mode=enums.ParseMode.HTML
            )
        try:
            btn = [[InlineKeyboardButton('📌 ᴊᴏɪɴ ᴜᴘᴅᴀᴛᴇꜱ ᴄʜᴀɴɴᴇʟ 📌', url=UPDATE_CHNL_LNK)]]
            msg = await client.send_cached_media(
                chat_id=message.from_user.id,
                file_id=file_id,
                protect_content=get_protect_content(),
                reply_markup=InlineKeyboardMarkup(btn))

            if not is_premium_user:
                await db.increase_download(message.from_user.id)

            filetype = msg.media
            file = getattr(msg, filetype.value)
            f_caption = build_file_caption(file.file_name, file.file_size)
            await msg.edit_caption(
                f_caption,
                reply_markup=InlineKeyboardMarkup(btn)
            )
            k = await msg.reply(script.DEL_MSG.format(get_time(DELETE_TIME)),
            quote=True, parse_mode=enums.ParseMode.HTML
            )
            await asyncio.sleep(DELETE_TIME)
            await msg.delete()
            await k.edit_text("<b>ʏᴏᴜʀ ᴠɪᴅᴇᴏ / ꜰɪʟᴇ ɪꜱ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ᴅᴇʟᴇᴛᴇᴅ !!\nᴋɪɴᴅʟʏ ꜱᴇᴀʀᴄʜ ᴀɢᴀɪɴ 😉</b>")
            return
        except Exception as e:
            logger.exception(e)
            pass
        return await message.reply('ɴᴏ ꜱᴜᴄʜ ꜰɪʟᴇ ᴇxɪꜱᴛꜱ !')

    # --- Daily Download Limit System: check before sending the file ---
    allowed, is_premium_user, remaining = await enforce_daily_limit(client, message)
    if not allowed:
        return

    # Show remaining limit BEFORE the file is sent
    if not is_premium_user:
        await message.reply_text(
            script.REMAINING_LIMIT_TXT.format(max(remaining - 1, 0), DAILY_DOWNLOAD_LIMIT),
            parse_mode=enums.ParseMode.HTML
        )

    files = files_[0]
    f_caption = build_file_caption(files.file_name, files.file_size, files.caption)
    btn = [[InlineKeyboardButton('📌 ᴊᴏɪɴ ᴜᴘᴅᴀᴛᴇꜱ ᴄʜᴀɴɴᴇʟ 📌', url=UPDATE_CHNL_LNK)]]
    cover_url = getattr(files, 'cover', None) if COVERX else None
    msg = await client.send_cached_media(
        chat_id=message.from_user.id,
        file_id=file_id,
        caption=f_caption,
        protect_content=get_protect_content(),
        reply_markup=InlineKeyboardMarkup(btn),
        cover=cover_url
    )
    if not is_premium_user:
        await db.increase_download(message.from_user.id)
    k = await msg.reply(script.DEL_MSG.format(get_time(DELETE_TIME)),
            quote=True, parse_mode=enums.ParseMode.HTML
    )     
    await asyncio.sleep(DELETE_TIME)
    await msg.delete()
    await k.edit_text("<b>ʏᴏᴜʀ ᴠɪᴅᴇᴏ / ꜰɪʟᴇ ɪꜱ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ᴅᴇʟᴇᴛᴇᴅ !!\nᴋɪɴᴅʟʏ ꜱᴇᴀʀᴄʜ ᴀɢᴀɪɴ 😉</b>")
    return


@Client.on_message(filters.command('logs') & filters.user(ADMINS))
async def log_file(bot, message):
    """Send log file"""
    try:
        await message.reply_document('DreamXlogs.txt', caption="📑 **ʟᴏɢꜱ**")
    except Exception as e:
        await message.reply(str(e))

@Client.on_message(filters.command('delete') & filters.user(ADMINS))
async def delete(bot, message):
    """Delete file from database"""
    reply = message.reply_to_message
    if reply and reply.media:
        msg = await message.reply("Pʀᴏᴄᴇssɪɴɢ...⏳", quote=True)
    else:
        await message.reply('Rᴇᴘʟʏ ᴛᴏ ғɪʟᴇ ᴡɪᴛʜ /delete ᴡʜɪᴄʜ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴅᴇʟᴇᴛᴇ', quote=True)
        return

    for file_type in ("document", "video", "audio"):
        media = getattr(reply, file_type, None)
        if media is not None:
            break
    else:
        await msg.edit('Tʜɪs ɪs ɴᴏᴛ sᴜᴘᴘᴏʀᴛᴇᴅ ғɪʟᴇ ғᴏʀᴍᴀᴛ')
        return

    file_id, file_ref = unpack_new_file_id(media.file_id)

    # 1. Sabse pehle exact file_id se try karo (sabhi configured DBs mein)
    deleted_count = await delete_file_by_id(file_id)

    if not deleted_count:
        # 2. Fallback: cleaned file_name + size + mime se try karo
        file_name = re.sub(r"(_|\-|\.|\+)", " ", str(media.file_name))
        deleted_count = await delete_files_by_query({
            'file_name': file_name,
            'file_size': media.file_size,
            'mime_type': media.mime_type
        })

    if not deleted_count:
        # 3. Fallback: raw file_name + size + mime se try karo
        deleted_count = await delete_files_by_query({
            'file_name': media.file_name,
            'file_size': media.file_size,
            'mime_type': media.mime_type
        })

    if deleted_count:
        await msg.edit('Fɪʟᴇ ɪs sᴜᴄᴄᴇssғᴜʟʟʏ ᴅᴇʟᴇᴛᴇᴅ ғʀᴏᴍ ᴅᴀᴛᴀʙᴀsᴇ ✅')
    else:
        await msg.edit('Fɪʟᴇ ɴᴏᴛ ғᴏᴜɴᴅ ɪɴ ᴅᴀᴛᴀʙᴀsᴇ ❌')


@Client.on_message(filters.command('deleteall') & filters.user(ADMINS))
async def delete_all_index(bot, message):
    await message.reply_text(
        'ᴛʜɪꜱ ᴡɪʟʟ ᴅᴇʟᴇᴛᴇ ᴀʟʟ ʏᴏᴜʀ ɪɴᴅᴇxᴇᴅ ꜰɪʟᴇꜱ !\nᴅᴏ ʏᴏᴜ ꜱᴛɪʟʟ ᴡᴀɴᴛ ᴛᴏ ᴄᴏɴᴛɪɴᴜᴇ ?',
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        text="⚠️ ʏᴇꜱ ⚠️", callback_data="autofilter_delete"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="❌ ɴᴏ ❌", callback_data="close_data"
                    )
                ],
            ]
        ),
        quote=True,
    )

@Client.on_message(filters.command('settings'))
async def settings(client, message):
    user_id = message.from_user.id if message.from_user else None
    if not user_id:
        return await message.reply(f"ʏᴏᴜ'ʀᴇ ᴀɴᴏɴʏᴍᴏᴜꜱ ᴀᴅᴍɪɴ.")
    chat_type = message.chat.type
    if chat_type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        grp_id = message.chat.id
        if not await is_check_admin(client, grp_id, message.from_user.id):
            return await message.reply_text(script.NT_ADMIN_ALRT_TXT)
        await db.connect_group(grp_id, user_id)
        btn = [[
                InlineKeyboardButton("👤 ᴏᴘᴇɴ ɪɴ ᴘʀɪᴠᴀᴛᴇ ᴄʜᴀᴛ 👤", callback_data=f"opnsetpm#{grp_id}")
              ],[
                InlineKeyboardButton("👥 ᴏᴘᴇɴ ʜᴇʀᴇ 👥", callback_data=f"opnsetgrp#{grp_id}")
              ]]
        await message.reply_text(
                text="<b>ᴡʜᴇʀᴇ ᴅᴏ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴏᴘᴇɴ ꜱᴇᴛᴛɪɴɢꜱ ᴍᴇɴᴜ ? ⚙️</b>",
                reply_markup=InlineKeyboardMarkup(btn),
                disable_web_page_preview=True,
                parse_mode=enums.ParseMode.HTML,
                reply_to_message_id=message.id
        )
    elif chat_type == enums.ChatType.PRIVATE:
        connected_groups = await db.get_connected_grps(user_id)
        if not connected_groups:
            return await message.reply_text("Nᴏ Cᴏɴɴᴇᴄᴛᴇᴅ Gʀᴏᴜᴘs Fᴏᴜɴᴅ .")
        group_list = []
        for group in connected_groups:
            try:
                Chat = await client.get_chat(group)
                group_list.append([ InlineKeyboardButton(text=Chat.title, callback_data=f"grp_pm#{Chat.id}") ])
            except Exception as e:
                print(f"Error In PM Settings Button - {e}")
                pass
        await message.reply_text(
                    "⚠️ ꜱᴇʟᴇᴄᴛ ᴛʜᴇ ɢʀᴏᴜᴘ ᴡʜᴏꜱᴇ ꜱᴇᴛᴛɪɴɢꜱ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴄʜᴀɴɢᴇ.\n\n"
                    "ɪꜰ ʏᴏᴜʀ ɢʀᴏᴜᴘ ɪꜱ ɴᴏᴛ ꜱʜᴏᴡɪɴɢ ʜᴇʀᴇ,\n"
                    "ᴜꜱᴇ /reload ɪɴ ᴛʜᴀᴛ ɢʀᴏᴜᴘ ᴀɴᴅ ɪᴛ ᴡɪʟʟ ᴀᴘᴘᴇᴀʀ ʜᴇʀᴇ.",
                    reply_markup=InlineKeyboardMarkup(group_list)
                )

@Client.on_message(filters.command('reload'))
async def connect_group(client, message):
    user_id = message.from_user.id
    if message.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        await db.connect_group(message.chat.id, user_id)
        await message.reply_text("Gʀᴏᴜᴘ Rᴇʟᴏᴀᴅᴇᴅ ✅ Nᴏᴡ Yᴏᴜ Cᴀɴ Mᴀɴᴀɢᴇ Tʜɪs Gʀᴏᴜᴘ Fʀᴏᴍ PM.")
    elif message.chat.type == enums.ChatType.PRIVATE:
        if len(message.command) < 2:
            await message.reply_text("Example: /reload 123456789")
            return
        try:
            group_id = int(message.command[1])
            if not await is_check_admin(client, group_id, user_id):
                await message.reply_text(script.NT_ADMIN_ALRT_TXT)
                return
            chat = await client.get_chat(group_id)
            await db.connect_group(group_id, user_id)
            await message.reply_text(f"Lɪɴᴋᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ ✅ {chat.title} ᴛᴏ PM.")
        except:
            await message.reply_text("Invalid group ID or error occurred.")

@Client.on_message(filters.command('set_template'))
async def save_template(client, message):
    sts = await message.reply("ᴄʜᴇᴄᴋɪɴɢ ᴛᴇᴍᴘʟᴀᴛᴇ...")
    user_id = message.from_user.id if message.from_user else None
    if not user_id:
        return await message.reply("ʏᴏᴜ'ʀᴇ ᴀɴᴏɴʏᴍᴏᴜꜱ ᴀᴅᴍɪɴ.")

    if message.chat.type not in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        return await sts.edit("⚠️ ᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ ɪɴ ᴀ ɢʀᴏᴜᴘ ᴄʜᴀᴛ.")

    group_id = message.chat.id
    title = message.chat.title
    if not await is_check_admin(client, group_id, user_id):
        await message.reply_text(script.NT_ADMIN_ALRT_TXT)
        return
    if len(message.command) < 2:
        return await sts.edit("⚠️ ɴᴏ ᴛᴇᴍᴘʟᴀᴛᴇ ᴘʀᴏᴠɪᴅᴇᴅ!")

    template = message.text.split(" ", 1)[1]
    await save_group_settings(group_id, 'template', template)
    await sts.edit(
        f"✅ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ᴜᴘᴅᴀᴛᴇᴅ ᴛᴇᴍᴘʟᴀᴛᴇ ꜰᴏʀ <code>{title}</code> ᴛᴏ:\n\n{template}"
    )

 #-----------------------------------------
# Must add REQST_CHANNEL to use this feature
# Universal Filter: Jo message mein kahin bhi command hone par trigger ho jaye
#-----------------------------------------

request_filter = filters.regex(r"(?i)(/request|#request)")

@Client.on_message(request_filter & filters.group)
async def requests(bot, message):
    # Agar Request Channel set nahi hai toh return ho jaye
    if REQST_CHANNEL is None:
        return

    reporter = str(message.from_user.id)
    mention = message.from_user.mention
    group_name = message.chat.title
    success = False
    reported_post = None

    # --- 1. CLEANING PROCESS ---
    # Message se @usernames aur commands ko remove karna
    raw_text = message.text or message.caption or ""
    clean_content = re.sub(r"@\w+", "", raw_text)
    clean_content = re.sub(r"(?i)/request|#request", "", clean_content).strip()

    # --- 2. LOGIC SELECTION (Reply vs Direct) ---
    if message.reply_to_message:
        # Reply hone par us message ka text lena
        content = message.reply_to_message.text or message.reply_to_message.caption or ""
        source_link = message.reply_to_message.link
    else:
        # Direct text hone par cleaned content lena
        content = clean_content
        source_link = message.link

    # --- 3. VALIDATION & HINDI-ENGLISH TEMPLATE ---
    if not content or len(content) < 3:
        template_text = (
            "<b>❌ अपनी मूवी या सीरीज का नाम तो लिखिये!</b>\n"

"<code>━━━━━━━━━━━━━━━━━━━━━</code>\n"
            "<b>📝 सही तरीका (Format):</b>\n"
            "<code>/request [Name] [Year] [Lang]</code>\n\n"
            "<b>🎬 मूवी का उदाहरण (Movie Example):</b>\n"
            "<blockquote><code>/request Stree 2 2024 Hindi</code></blockquote>\n\n"
            "<b>📺 सीरीज का उदाहरण (Series Example):</b>\n"
            "<blockquote><code>/request Mirzapur S03 Hindi</code></blockquote>\n"
            "<code>━━━━━━━━━━━━━━━━━━━━━</code>\n"
            "<b>✨ Tip:</b> <i>Msg पर Reply करके भी Request कर सकते हैं।</i>"
        )
        error_msg = await message.reply_text(template_text)
        await asyncio.sleep(60) # 1 min auto-delete
        await error_msg.delete()
        await message.delete()
        return

    # --- 4. SENDING REQUEST TO ADMIN/CHANNEL ---
    try:
        btn_admin = [[
            InlineKeyboardButton('👁️ᴠɪᴇᴡ ʀᴇǫᴜᴇꜱᴛ👁️', url=f"{source_link}"),
            InlineKeyboardButton('💢ꜱʜᴏᴡ ᴏᴘᴛɪᴏɴꜱ💢', callback_data=f'show_option#{reporter}')
        ]]

        request_text = (
            f"<b>🎬 ʀᴇǫᴜᴇꜱᴛ : <code>{content}</code>\n\n"
            f"👤 ʀᴇᴘᴏʀᴛᴇᴅ ʙʏ : {mention}\n"
            f"🆔 ʀᴇᴘᴏʀᴛᴇʀ ɪᴅ : <code>{reporter}</code>\n"
            f"👥 ɢʀᴏᴜᴘ ɴᴀᴍᴇ : <code>{group_name}</code>\n\n"
            f"#ʀᴇǫᴜᴇꜱᴛ ⚡️</b>"
        )

        if REQST_CHANNEL:
            reported_post = await bot.send_message(
                chat_id=REQST_CHANNEL, 
                text=request_text, 
                reply_markup=InlineKeyboardMarkup(btn_admin)
            )
            success = True
        elif ADMINS:
            for admin in ADMINS:
                reported_post = await bot.send_message(
                    chat_id=admin, 
                    text=request_text, 
                    reply_markup=InlineKeyboardMarkup(btn_admin)
                )
            success = True

    except Exception as e:
        await message.reply_text(f"<b>ᴇʀʀᴏʀ:</b> <code>{e}</code>")
        return

    # --- 5. USER NOTIFICATION & AUTO-DELETE ---
    if success and reported_post:
        try:
            link = await bot.create_chat_invite_link(int(REQST_CHANNEL))
            btn_user = [[
                InlineKeyboardButton('ᴍᴏᴠɪᴇ ᴜᴘᴅᴀᴛᴇ ᴄʜᴀɴɴᴇʟ📢', url=MOVIE_UPDATE_CHANNEL_LINK),
                InlineKeyboardButton('ᴠɪᴇᴡ ʀᴇǫᴜᴇꜱᴛ👁‍🗨', url=f"{reported_post.link}")
            ]]

            confirm_msg = await message.reply_text(
                "<b>✅ आपकी रिक्वेस्ट सफलतापूर्वक भेज दी गई है!\n\n"
                "⌛ थोड़ा इंतज़ार (Wait) कीजिये...\n"
                "📢 नीचे दिए गए बटन पर क्लिक करके चैनल Join करें available होते ही यहां Post डाल दी जाएगी और अपनी ᴠɪᴇᴡ ʀᴇǫᴜᴇꜱᴛ पर रिक्वेस्ट चेक कर सकते हो।</b>",
                reply_markup=InlineKeyboardMarkup(btn_user)
            )

            # 60 seconds baad command aur response dono delete ho jayenge
            await asyncio.sleep(60)
            await confirm_msg.delete()
            await message.delete()
        except:
            pass




@Client.on_message(filters.command("send") & filters.user(ADMINS))
async def send_msg(bot, message):
    # Usage: reply to any message with /send USER_ID
    if not message.reply_to_message:
        await message.reply_text(
            "<b>ᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ ᴀꜱ ᴀ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴍᴇꜱꜱᴀɢᴇ.\n\n"
            "Example: <code>/send 123456789</code></b>"
        )
        raise StopPropagation

    if len(message.command) < 2:
        await message.reply_text(
            "<b>❌ ᴜꜱᴇʀ ɪᴅ ᴍɪꜱꜱɪɴɢ.\n\n"
            "Example: <code>/send 123456789</code></b>"
        )
        raise StopPropagation

    try:
        target_id = int(message.command[1])
    except (ValueError, TypeError):
        await message.reply_text("<b>❌ ɪɴᴠᴀʟɪᴅ ᴜꜱᴇʀ ɪᴅ.</b>")
        raise StopPropagation

    try:
        user = await bot.get_users(target_id)
        users = await db.get_all_users()
        saved_user = False

        async for usr in users:
            if int(usr.get("id", 0)) == target_id:
                saved_user = True
                break

        if not saved_user:
            await message.reply_text(
                "<b>ᴛʜɪꜱ ᴜꜱᴇʀ ᴅɪᴅɴ'ᴛ ꜱᴛᴀʀᴛ ᴛʜɪꜱ ʙᴏᴛ ʏᴇᴛ !</b>"
            )
            raise StopPropagation

        await message.reply_to_message.copy(chat_id=target_id)
        await message.reply_text(
            f"<b>ʏᴏᴜʀ ᴍᴇꜱꜱᴀɢᴇ ʜᴀꜱ ʙᴇᴇɴ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ꜱᴇɴᴛ ᴛᴏ {user.mention}.</b>"
        )
    except StopPropagation:
        raise
    except Exception as e:
        await message.reply_text(f"<b>❌ Error: {e}</b>")

    raise StopPropagation


@Client.on_message(filters.command("deletefiles") & filters.user(ADMINS))
async def deletemultiplefiles(bot, message):
    chat_type = message.chat.type
    if chat_type != enums.ChatType.PRIVATE:
        return await message.reply_text(f"<b>Hey {message.from_user.mention}, This command won't work in groups. It only works on my PM !</b>")
    else:
        pass
    try:
        keyword = message.text.split(" ", 1)[1]
    except:
        return await message.reply_text(f"<b>Hey {message.from_user.mention}, Give me a keyword along with the command to delete files.</b>")
    k = await bot.send_message(chat_id=message.chat.id, text=f"<b>Fetching Files for your query {keyword} on DB... Please wait...</b>")
    files, total = await get_bad_files(keyword)
    total = len(files)
    if total == 0:
        await k.edit_text(f"<b>No files found for your query {keyword} !</b>")
        await asyncio.sleep(DELETE_TIME)
        await k.delete()
        return
    await k.delete()
    btn = [[
       InlineKeyboardButton("⚠️ Yes, Continue ! ⚠️", callback_data=f"killfilesdq#{keyword}")
       ],[
       InlineKeyboardButton("❌ No, Abort operation ! ❌", callback_data="close_data")
    ]]
    await message.reply_text(
        text=f"<b>Found {total} files for your query {keyword} !\n\nDo you want to delete?</b>",
        reply_markup=InlineKeyboardMarkup(btn),
        parse_mode=enums.ParseMode.HTML
    )


@Client.on_callback_query(filters.regex("topsearch"))
async def topsearch_callback(client, callback_query):
    def is_alphanumeric(string):
        return bool(re.match('^[a-zA-Z0-9 ]*$', string))

    limit = 20  
    top_messages = await mdb.get_top_messages(limit)
    seen_messages = set()
    truncated_messages = []
    for msg in top_messages:
        msg_lower = msg.lower()
        if msg_lower not in seen_messages and is_alphanumeric(msg):
            seen_messages.add(msg_lower)
            if len(msg) > 35:
                truncated_messages.append(msg[:32] + "...")
            else:
                truncated_messages.append(msg)
    keyboard = [truncated_messages[i:i+2] for i in range(0, len(truncated_messages), 2)]
    reply_markup = ReplyKeyboardMarkup(
        keyboard, 
        one_time_keyboard=True, 
        resize_keyboard=True, 
        placeholder="Most searches of the day"
    )
    await callback_query.message.reply_text(
        "<b>Tᴏᴘ Sᴇᴀʀᴄʜᴇs Oғ Tʜᴇ Dᴀʏ 👇</b>",
        reply_markup=reply_markup
    )
    await callback_query.answer()

@Client.on_message(filters.command('top_search'))
async def top(_, message):
    def is_alphanumeric(string):
        return bool(re.match('^[a-zA-Z0-9 ]*$', string))
    try:
        limit = int(message.command[1])
    except (IndexError, ValueError):
        limit = 20
    top_messages = await mdb.get_top_messages(limit)
    seen_messages = set()
    truncated_messages = []
    for msg in top_messages:
        msg_lower = msg.lower()
        if msg_lower not in seen_messages and is_alphanumeric(msg):
            seen_messages.add(msg_lower)
            if len(msg) > 35:
                truncated_messages.append(msg[:32] + "...")
            else:
                truncated_messages.append(msg)
    keyboard = [truncated_messages[i:i+2] for i in range(0, len(truncated_messages), 2)]
    reply_markup = ReplyKeyboardMarkup(
        keyboard, 
        one_time_keyboard=True, 
        resize_keyboard=True, 
        placeholder="Most searches of the day"
    )
    await message.reply_text(
        "<b>Tᴏᴘ Sᴇᴀʀᴄʜᴇs Oғ Tʜᴇ Dᴀʏ 👇</b>",
        reply_markup=reply_markup
    )

@Client.on_message(filters.command('trendlist'))
async def trendlist(client, message):
    def is_alphanumeric(string):
        return bool(re.match('^[a-zA-Z0-9 ]*$', string))
    limit = 31
    if len(message.command) > 1:
        try:
            limit = int(message.command[1])
        except ValueError:
            await message.reply_text(
                "Invalid number format.\nPlease provide a valid number after the /trendlist command."
            )
            return 
    try:
        top_messages = await mdb.get_top_messages(limit)
    except Exception as e:
        await message.reply_text(f"Error retrieving messages: {str(e)}")
        return  

    if not top_messages:
        await message.reply_text("No top messages found.")
        return 
    seen_messages = set()
    truncated_messages = []

    for msg in top_messages:
        msg_lower = msg.lower()
        if msg_lower not in seen_messages and is_alphanumeric(msg):
            seen_messages.add(msg_lower)
            truncated_messages.append(msg[:32] + '...' if len(msg) > 35 else msg)

    if not truncated_messages:
        await message.reply_text("No valid top messages found.")
        return  
    formatted_list = "\n".join([f"{i+1}. <b>{msg}</b>" for i, msg in enumerate(truncated_messages)])
    additional_message = (
        "⚡️ 𝑨𝒍𝒍 𝒕𝒉𝒆 𝒓𝒆𝒔𝒖𝒍𝒕𝒔 𝒂𝒃𝒐𝒗𝒆 𝒄𝒐𝒎𝒆 𝒇𝒓𝒐𝒎 𝒘𝒉𝒂𝒕 𝒖𝒔𝒆𝒓𝒔 𝒉𝒂𝒗𝒆 𝒔𝒆𝒂𝒓𝒄𝒉𝒆𝒅 𝒇𝒐𝒓. "
        "𝑻𝒉𝒆𝒚'𝒓𝒆 𝒔𝒉𝒐𝒘𝒏 𝒕𝒐 𝒚𝒐𝒖 𝒆𝒙𝒂𝒄𝒕𝒍𝒚 𝒂𝒔 𝒕𝒉𝒆𝒚 𝒘𝒆𝒓𝒆 𝒔𝒆𝒂𝒓𝒄𝒉𝒆𝒅, "
        "𝒘𝒊𝒕𝒉𝒐𝒖𝒕 𝒂𝒏𝒚 𝒄𝒉𝒂𝒏𝒈𝒆𝒔 𝒃𝒚 𝒕𝒉𝒆 𝒐𝒘𝒏𝒆𝒓."
    )
    formatted_list += f"\n\n{additional_message}"
    reply_text = f"<b>Top {len(truncated_messages)} Tʀᴀɴᴅɪɴɢ ᴏғ ᴛʜᴇ ᴅᴀʏ 👇:</b>\n\n{formatted_list}"
    await message.reply_text(reply_text)

@Client.on_message(filters.private & filters.command("pm_search") & filters.user(ADMINS))
async def set_pm_search(client, message):
    bot_id = client.me.id
    try:
        option = message.text.split(" ", 1)[1].strip().lower()
        enable_status = option in ['on', 'true']
    except (IndexError, ValueError):
        await message.reply_text("<b>💔 Invalid option. Please send 'on' or 'off' after the command..</b>")
        return
    try:
        await db.update_pm_search_status(bot_id, enable_status)
        response_text = (
            "<b> ᴘᴍ ꜱᴇᴀʀᴄʜ ᴇɴᴀʙʟᴇᴅ ✅</b>" if enable_status 
            else "<b> ᴘᴍ ꜱᴇᴀʀᴄʜ ᴅɪꜱᴀʙʟᴇᴅ ❌</b>"
        )
        await message.reply_text(response_text)
    except Exception as e:
        logger.error(f"Error in set_pm_search: {e}")
        await message.reply_text(f"<b>❗ An error occurred: {e}</b>")

@Client.on_message(filters.private & filters.command("movie_update") & filters.user(ADMINS))
async def set_movie_update_notification(client, message):
    bot_id = client.me.id
    try:
        option = message.text.split(" ", 1)[1].strip().lower()
        enable_status = option in ['on', 'true']
    except (IndexError, ValueError):
        await message.reply_text("<b>💔 Invalid option. Please send 'on' or 'off' after the command.</b>")
        return
    try:
        await db.update_movie_update_status(bot_id, enable_status)
        response_text = (
            "<b>ᴍᴏᴠɪᴇ ᴜᴘᴅᴀᴛᴇ ɴᴏᴛɪꜰɪᴄᴀᴛɪᴏɴ ᴇɴᴀʙʟᴇᴅ ✅</b>" if enable_status 
            else "<b>ᴍᴏᴠɪᴇ ᴜᴘᴅᴀᴛᴇ ɴᴏᴛɪꜰɪᴄᴀᴛɪᴏɴ ᴅɪꜱᴀʙʟᴇᴅ ❌</b>"
        )
        await message.reply_text(response_text)
    except Exception as e:
        logger.error(f"Error in set_movie_update_notification: {e}")
        await message.reply_text(f"<b>❗ An error occurred: {e}</b>")

@Client.on_message(filters.command("restart") & filters.user(ADMINS))
async def stop_button(bot, message):
    msg = await bot.send_message(text="<b><i>ʙᴏᴛ ɪꜱ ʀᴇꜱᴛᴀʀᴛɪɴɢ</i></b>", chat_id=message.chat.id)       
    await asyncio.sleep(3)
    await msg.edit("<b><i><u>ʙᴏᴛ ɪꜱ ʀᴇꜱᴛᴀʀᴛᴇᴅ</u> ✅</i></b>")
    os.execl(sys.executable, sys.executable, *sys.argv)

@Client.on_message(filters.command("del_msg") & filters.user(ADMINS))
async def del_msg(client, message):
    confirm_markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("Yes", callback_data="confirm_del_yes"),
        InlineKeyboardButton("No", callback_data="confirm_del_no")
    ]])
    sent_message = await message.reply_text(
        "⚠️ Aʀᴇ ʏᴏᴜ sᴜʀᴇ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴄʟᴇᴀʀ ᴛʜᴇ ᴜᴘᴅᴀᴛᴇs ᴄʜᴀɴɴᴇʟ ʟɪsᴛ ?\n\n ᴅᴏ ʏᴏᴜ ꜱᴛɪʟʟ ᴡᴀɴᴛ ᴛᴏ ᴄᴏɴᴛɪɴᴜᴇ ?",
        reply_markup=confirm_markup
    )
    await asyncio.sleep(60)
    try:
        await sent_message.delete()
    except Exception as e:
        print(f"Error deleting the message: {e}")

@Client.on_callback_query(filters.regex('^confirm_del_'))
async def confirmation_handler(client, callback_query):
    action = callback_query.data.split("_")[-1] 
    if action == "yes":
        await db.delete_all_msg()  
        await callback_query.message.edit_text('🧹 ᴜᴘᴅᴀᴛᴇꜱ ᴄʜᴀɴɴᴇʟ ʟɪsᴛ ʜᴀs ʙᴇᴇɴ ᴄʟᴇᴀʀᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ ✅')
    elif action == "no":
        await callback_query.message.delete()  
    await callback_query.answer()

@Client.on_message(filters.command('details'))
async def all_settings(client, message):
    if message.chat.type not in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        return await message.reply_text("<b>ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪɴ ɢʀᴏᴜᴘ...</b>")
    grp_id = message.chat.id
    title = message.chat.title
    if not await is_check_admin(client, grp_id, message.from_user.id):
        return await message.reply_text(script.NT_ADMIN_ALRT_TXT)
    try:
        settings = await get_settings(grp_id)
    except Exception as e:
        return await message.reply_text(f"<b>⚠️ ᴇʀʀᴏʀ ꜰᴇᴛᴄʜɪɴɢ ꜱᴇᴛᴛɪɴɢꜱ:</b>\n<code>{e}</code>")
    text = generate_settings_text(settings, title)
    btn = [
        [InlineKeyboardButton("♻️ ʀᴇꜱᴇᴛ ꜱᴇᴛᴛɪɴɢꜱ", callback_data=f"reset_group_{grp_id}")],
        [InlineKeyboardButton("🚫 ᴄʟᴏꜱᴇ", callback_data="close_data")]
    ]
    dlt = await message.reply_text(text, reply_markup=InlineKeyboardMarkup(btn), disable_web_page_preview=True)
    await asyncio.sleep(300)
    await dlt.delete()

@Client.on_callback_query(filters.regex(r"^reset_group_(\-\d+)$"))
async def reset_group_callback(client, callback_query):
    grp_id = int(callback_query.matches[0].group(1))
    user_id = callback_query.from_user.id
    if not await is_check_admin(client, grp_id, user_id):
        return await callback_query.answer(script.NT_ADMIN_ALRT_TXT, show_alert=True)
    await callback_query.answer("♻️ ʀᴇꜱᴇᴛᴛɪɴɢ ꜱᴇᴛᴛɪɴɢꜱ...")
    defaults = {
        'template': IMDB_TEMPLATE,
        'fsub': AUTH_CHANNELS
    }
    current = await get_settings(grp_id)
    if current == defaults:
        return await callback_query.answer("✅ ꜱᴇᴛᴛɪɴɢꜱ ᴀʟʀᴇᴀᴅʏ ᴅᴇꜰᴀᴜʟᴛ.", show_alert=True)
    for key, value in defaults.items():
        await save_group_settings(grp_id, key, value)
    updated = await get_settings(grp_id)
    title = callback_query.message.chat.title
    text = generate_settings_text(updated, title, reset_done=True)
    buttons = [
        [InlineKeyboardButton("♻️ ʀᴇꜱᴇᴛ ꜱᴇᴛᴛɪɴɢꜱ", callback_data=f"reset_group_{grp_id}")],
        [InlineKeyboardButton("🚫 ᴄʟᴏꜱᴇ", callback_data="close_data")]
    ]
    await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)

@Client.on_message(filters.command('set_fsub'))
async def set_fsub(client, message):
    try:
        userid = message.from_user.id if message.from_user else None
        if not userid:
            return await message.reply("<b>You are Anonymous admin you can't use this command !</b>")
        if message.chat.type not in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
            return await message.reply_text("ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ᴄᴀɴ ᴏɴʟʏ ʙᴇ ᴜsᴇᴅ ɪɴ ɢʀᴏᴜᴘs")
        grp_id = message.chat.id
        title = message.chat.title
        if not await is_check_admin(client, grp_id, userid):
            return await message.reply_text(script.NT_ADMIN_ALRT_TXT)
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            return await message.reply_text(
                "ᴄᴏᴍᴍᴀɴᴅ ɪɴᴄᴏᴍᴘʟᴇᴛᴇ!\n\n"
                "ᴄᴀɴ ᴀᴅᴅ ᴍᴜʟᴛɪᴘʟᴇ ᴄʜᴀɴɴᴇʟs sᴇᴘᴀʀᴀᴛᴇᴅ ʙʏ sᴘᴀᴄᴇs. ʟɪᴋᴇ: /sᴇᴛ_ғsᴜʙ ɪᴅ1 ɪᴅ2 ɪᴅ3\n"
            )
        option = args[1].strip()
        try:
            fsub_ids = [int(x) for x in option.split()]
        except ValueError:
            return await message.reply_text('ᴍᴀᴋᴇ sᴜʀᴇ ᴀʟʟ ɪᴅs ᴀʀᴇ ɪɴᴛᴇɢᴇʀs.')
        if len(fsub_ids) > 5:
            return await message.reply_text("ᴍᴀxɪᴍᴜᴍ 5 ᴄʜᴀɴɴᴇʟs ᴀʟʟᴏᴡᴇᴅ.")
        channels = "ᴄʜᴀɴɴᴇʟs:\n"
        channel_titles = []
        for id in fsub_ids:
            try:
                chat = await client.get_chat(id)
            except Exception as e:
                return await message.reply_text(
                    f"{id} ɪs ɪɴᴠᴀʟɪᴅ!\nᴍᴀᴋᴇ sᴜʀᴇ ᴛʜɪs ʙᴏᴛ ɪs ᴀᴅᴍɪɴ ɪɴ ᴛʜᴀᴛ ᴄʜᴀɴɴᴇʟ.\n\nError - {e}"
                )
            if chat.type != enums.ChatType.CHANNEL:
                return await message.reply_text(f"{id} ɪs ɴᴏᴛ ᴀ ᴄʜᴀɴɴᴇʟ.")
            channel_titles.append(f"{chat.title} (`{id}`)")
            channels += f'{chat.title}\n'
        await save_group_settings(grp_id, 'fsub', fsub_ids)
        await message.reply_text(f"sᴜᴄᴄᴇssғᴜʟʟʏ sᴇᴛ ꜰꜱᴜʙ ᴄʜᴀɴɴᴇʟ(ꜱ) ғᴏʀ {title} ᴛᴏ\n\n{channels}")
        mention = message.from_user.mention if message.from_user else "Unknown"
        await client.send_message(
            LOG_API_CHANNEL,
            f"#Fsub_Channel_set\n\n"
            f"ᴜꜱᴇʀ - {mention} ꜱᴇᴛ ᴛʜᴇ ꜰᴏʀᴄᴇ ᴄʜᴀɴɴᴇʟ(ꜱ) ꜰᴏʀ {title}:\n\n"
            f"ꜰꜱᴜʙ ᴄʜᴀɴɴᴇʟ(ꜱ):\n" + '\n'.join(channel_titles)
        )
    except Exception as e:
        err_text = f"⚠️ Error in set_fSub :\n{e}"
        logger.error(err_text)
        await client.send_message(LOG_API_CHANNEL, err_text)

@Client.on_message(filters.command('remove_fsub'))
async def remove_fsub(client, message):
    try:
        userid = message.from_user.id if message.from_user else None
        if not userid:
            return await message.reply("<b>You are Anonymous admin you can't use this command !</b>")
        if message.chat.type not in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
            return await message.reply_text("ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ᴄᴀɴ ᴏɴʟʏ ʙᴇ ᴜsᴇᴅ ɪɴ ɢʀᴏᴜᴘs")
        grp_id = message.chat.id
        title = message.chat.title
        if not await is_check_admin(client, grp_id, userid):
            return await message.reply_text(script.NT_ADMIN_ALRT_TXT)

        settings = await get_settings(grp_id)
        current_fsub = settings.get('fsub', []) if settings else []

        if not current_fsub:
            return await message.reply_text("ᴛʜɪs ɢʀᴏᴜᴘ ʜᴀs ɴᴏ ᴄᴜsᴛᴏᴍ ꜰsᴜʙ ᴄʜᴀɴɴᴇʟ(s) sᴇᴛ.")

        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            # No IDs given -> clear ALL custom fsub channels for this group
            await save_group_settings(grp_id, 'fsub', AUTH_CHANNELS)
            await message.reply_text(f"sᴜᴄᴄᴇssғᴜʟʟʏ ʀᴇᴍᴏᴠᴇᴅ ᴀʟʟ ᴄᴜsᴛᴏᴍ ꜰsᴜʙ ᴄʜᴀɴɴᴇʟ(s) ꜰᴏʀ {title}.")
            log_note = "Aʟʟ ᴄᴜsᴛᴏᴍ ꜰsᴜʙ ᴄʜᴀɴɴᴇʟ(s) ʀᴇᴍᴏᴠᴇᴅ."
        else:
            # Specific channel IDs given -> remove only those
            option = args[1].strip()
            try:
                remove_ids = [int(x) for x in option.split()]
            except ValueError:
                return await message.reply_text('ᴍᴀᴋᴇ sᴜʀᴇ ᴀʟʟ ɪᴅs ᴀʀᴇ ɪɴᴛᴇɢᴇʀs.')
            not_found = [i for i in remove_ids if i not in current_fsub]
            updated_fsub = [i for i in current_fsub if i not in remove_ids]
            await save_group_settings(grp_id, 'fsub', updated_fsub)
            msg = f"sᴜᴄᴄᴇssғᴜʟʟʏ ʀᴇᴍᴏᴠᴇᴅ {len(remove_ids) - len(not_found)} ꜰsᴜʙ ᴄʜᴀɴɴᴇʟ(s) ꜰᴏʀ {title}."
            if not_found:
                msg += f"\n\n⚠️ ɴᴏᴛ ꜰᴏᴜɴᴅ ɪɴ ʟɪsᴛ: {', '.join(str(i) for i in not_found)}"
            await message.reply_text(msg)
            log_note = f"Rᴇᴍᴏᴠᴇᴅ ꜰsᴜʙ ᴄʜᴀɴɴᴇʟ(s): {', '.join(str(i) for i in remove_ids)}"

        mention = message.from_user.mention if message.from_user else "Unknown"
        await client.send_message(
            LOG_API_CHANNEL,
            f"#Fsub_Channel_removed\n\n"
            f"ᴜꜱᴇʀ - {mention} ᴜᴘᴅᴀᴛᴇᴅ ᴛʜᴇ ꜰᴏʀᴄᴇ ᴄʜᴀɴɴᴇʟ(ꜱ) ꜰᴏʀ {title}:\n\n{log_note}"
        )
    except Exception as e:
        err_text = f"⚠️ Error in remove_fsub :\n{e}"
        logger.error(err_text)
        await client.send_message(LOG_API_CHANNEL, err_text)


@Client.on_message(filters.private & filters.command("resetallgroup") & filters.user(ADMINS))
async def reset_all_settings(client, message):
    try:
        reset_count = await db.dreamx_reset_settings()
        await message.reply_text(
            f"<b>ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ᴅᴇʟᴇᴛᴇᴅ ꜱᴇᴛᴛɪɴɢꜱ ꜰᴏʀ  <code>{reset_count}</code> ɢʀᴏᴜᴘꜱ. ᴅᴇꜰᴀᴜʟᴛ ᴠᴀʟᴜᴇꜱ ᴡɪʟʟ ʙᴇ ᴜꜱᴇᴅ ✅</b>",
            quote=True
        )
    except Exception as e:
        print(f"[ERROR] reset_all_settings: {e}")
        await message.reply_text(
            "<b>🚫 An error occurred while resetting group settings.\nPlease try again later.</b>",
            quote=True
        )

@Client.on_message(filters.command("trial_reset"))
async def reset_trial(client, message):
    user_id = message.from_user.id
    if user_id not in ADMINS:
        await message.reply("ʏᴏᴜ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴀɴʏ ᴘᴇʀᴍɪꜱꜱɪᴏɴ ᴛᴏ ᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ.")
        return
    try:
        if len(message.command) > 1:
            target_user_id = int(message.command[1])
            updated_count = await db.reset_free_trial(target_user_id)
            message_text = f"ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ʀᴇꜱᴇᴛ ꜰʀᴇᴇ ᴛʀᴀɪʟ ꜰᴏʀ ᴜꜱᴇʀꜱ {target_user_id}." if updated_count else f"ᴜꜱᴇʀ {target_user_id} ɴᴏᴛ ꜰᴏᴜɴᴅ ᴏʀ ᴅᴏɴ'ᴛ ᴄʟᴀɪᴍ ꜰʀᴇᴇ ᴛʀᴀɪʟ ʏᴇᴛ."
        else:
            updated_count = await db.reset_free_trial()
            message_text = f"ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ʀᴇꜱᴇᴛ ꜰʀᴇᴇ ᴛʀᴀɪʟ ꜰᴏʀ {updated_count} ᴜꜱᴇʀꜱ."
        await message.reply_text(message_text)
    except Exception as e:
        await message.reply_text(f"An error occurred: {e}")

from motor.motor_asyncio import AsyncIOMotorClient

@Client.on_message(filters.command("old_cleandb") & filters.user(ADMINS))
async def clean_db_command(client, message):
    await message.reply_text("🧹 Cleaning database(s)... Please wait ⏳")

    try:
        fields_to_unset = {
            "file_ref": "",
            "file_type": "",
            "mime_type": "",
            "caption": ""
        }

        summary = []

        # === Clean every configured DB (1 to 5, based on MEDIA_DBS) ===
        for idx, media_cls in enumerate(MEDIA_DBS, start=1):
            result = await media_cls.collection.update_many({}, {"$unset": fields_to_unset})
            summary.append(f"🗃️ DB{idx} — Matched: <code>{result.matched_count}</code>, Modified: <code>{result.modified_count}</code>")

        if len(MEDIA_DBS) == 1:
            summary.append("⚙️ MULTIPLE_DB = False → Sirf DB1 hi configured/cleaned hua.")

        await message.reply_text(
            "✅ <b>Cleanup Complete!</b>\n\n" + "\n".join(summary)
        )

    except Exception as e:
        await message.reply_text(f"❌ <b>Error while cleaning DB:</b>\n<code>{e}</code>")


@Client.on_message(filters.command("cleandb") & filters.user(ADMINS))
async def clean_db_command(client, message):
    status_msg = await message.reply_text(
        "🧹 <b>Cleaning database(s)...</b>\n"
        "⏳ Please wait..."
    )

    try:
        fields_to_unset = {
            "file_ref": "",
            "file_type": "",
            "mime_type": "",
            "caption": ""
        }

        summary = []

        # Small batches to reduce MongoDB update pressure
        BATCH_SIZE = 100

        # Clean every configured DB (1 to 5)
        for idx, media_cls in enumerate(MEDIA_DBS, start=1):
            collection = media_cls.collection

            total_matched = 0
            total_modified = 0

            while True:
                # Only find documents which actually contain
                # at least one field that needs to be removed.
                docs = await collection.find(
                    {
                        "$or": [
                            {"file_ref": {"$exists": True}},
                            {"file_type": {"$exists": True}},
                            {"mime_type": {"$exists": True}},
                            {"caption": {"$exists": True}}
                        ]
                    },
                    {"_id": 1}
                ).limit(BATCH_SIZE).to_list(length=BATCH_SIZE)

                if not docs:
                    break

                ids = [doc["_id"] for doc in docs]

                result = await collection.update_many(
                    {"_id": {"$in": ids}},
                    {"$unset": fields_to_unset}
                )

                total_matched += result.matched_count
                total_modified += result.modified_count

                # Give MongoDB a little breathing room
                await asyncio.sleep(0.1)

                # Safety: avoid infinite loop
                if result.modified_count == 0:
                    break

            summary.append(
                f"🗃️ DB{idx} — "
                f"Matched: <code>{total_matched}</code>, "
                f"Modified: <code>{total_modified}</code>"
            )

        if len(MEDIA_DBS) == 1:
            summary.append(
                "⚙️ MULTIPLE_DB = False → "
                "Sirf DB1 configured/cleaned hua."
            )

        await status_msg.edit_text(
            "✅ <b>Cleanup Complete!</b>\n\n"
            + "\n".join(summary)
            + "\n\n"
            "📌 Files/documents delete nahi kiye gaye.\n"
            "🧹 Sirf unnecessary fields remove ki gayi hain."
        )

    except Exception as e:
        await status_msg.edit_text(
            "❌ <b>Error while cleaning DB:</b>\n"
            f"<code>{e}</code>"
        )
