#!/usr/bin/env python3

import telebot
from telebot import types
import logging

import model
import db_helper
import config
import strings

telebot.logger.setLevel(logging.WARNING)


# helper function: returns an array of InlineKeyboardButton for paginating stuff
# prefix - string added to each callback data from the front
# page_no - current page number
# pages_count - number of pages
# buttons_count - how many buttons should be returned
def pager_buttons(prefix, page_no, pages_count):
    if pages_count < 2:
        pages_count = 1
    if page_no < 1:
        page_no = 1
    if page_no > pages_count:
        page_no = pages_count

    marks = strings.pager_marks
    buttons_count = 5  # odd numbers recommended
    buttons = {}

    if pages_count > buttons_count:
        left = page_no - (buttons_count // 2)
        right = page_no + (buttons_count // 2)

        if left < 1:
            left = 1
            right = buttons_count
        if right > pages_count:
            right = pages_count
            left = pages_count - buttons_count + 1

        for i in range(left, right + 1):
            if i < page_no:
                buttons[i] = marks[1] + str(i)
            elif i == page_no:
                buttons[i] = marks[2] + str(i) + marks[2]
            elif i > page_no:
                buttons[i] = str(i) + marks[3]

        if buttons[left].startswith(marks[1]):
            del buttons[left]
            buttons[1] = marks[0] + '1'
        if buttons[right].endswith(marks[3]):
            del buttons[right]
            buttons[pages_count] = str(pages_count) + marks[4]

    else:
        for i in range(1, pages_count + 1):
            if i == page_no:
                buttons[i] = marks[2] + str(i) + marks[2]
            else:
                buttons[i] = str(i)

    button_row = [
        types.InlineKeyboardButton(
            text=buttons[key],
            callback_data=prefix + str(key)
        ) for key in sorted(buttons.keys())
        ]
    return button_row


class ProxyBot(telebot.TeleBot):
    def __init__(self, token, master_id):
        super().__init__(token)
        bot = self
        bot.remove_webhook()
        me = bot.get_me()
        self.id = me.id
        self.username = me.username
        self.master_id = master_id
        db = self.db = db_helper.DB(self.id)

        # helper decorator: wrapper around bot.message handler for catching all commands with specified prefix
        def my_commandset_handler(prefix):
            def test(m):
                return (
                    m.content_type == 'text' and
                    m.text.startswith('/' + prefix) and
                    m.chat.id == master_id
                )

            decorator = bot.message_handler(func=test)
            return decorator

        # helper function: returns an InlineKeyboard markup for chatview
        def get_chatview_markup(chat, log_page=None):
            markup = types.InlineKeyboardMarkup(row_width=3)
            buttons = []
            if log_page is not None:
                text = '{:html}\n\n'.format(chat)

                log_pages_count, msgs = db.msg.get_chat_page(chat.id, log_page)  # gets messages from db

                if log_page == 0:
                    log_page = log_pages_count  # if page_no is not set, let it be the last page

                for msg in msgs:
                    text += '{}\n'.format(msg)
                markup.row(*pager_buttons('log_{}_'.format(chat.id), log_page, log_pages_count))
                buttons.append(
                    types.InlineKeyboardButton(strings.btn.hide_log, callback_data='chat_hide_{}'.format(chat.id)))
            else:
                text = strings.msg.chat_full.format(chat=chat)
                buttons.append(
                    types.InlineKeyboardButton(strings.btn.show_log, callback_data='log_{}_0'.format(chat.id)))

            if chat.blocked:
                buttons.append(
                    types.InlineKeyboardButton(strings.btn.unblock, callback_data='chat_unblock_{}'.format(chat.id)))
            else:
                buttons.append(
                    types.InlineKeyboardButton(strings.btn.block, callback_data='chat_block_{}'.format(chat.id)))
            buttons.append(types.InlineKeyboardButton(strings.btn.reply, callback_data='reply_{}'.format(chat.id)))

            markup.add(*buttons)
            markup.add(types.InlineKeyboardButton(strings.btn.menu, callback_data='menu'))
            return text, markup

        @bot.message_handler(func=lambda m: m.chat.type != 'private')
        def leave(message):
            try:
                bot.reply_to(message, 'I work only in private chats')
            except telebot.apihelper.ApiException:
                pass
            bot.leave_chat(message.chat.id)

        @bot.message_handler(func=lambda message: message.chat.id == master_id, commands=['start'])
        def start_menu(message):
            if not db.common.messages:
                command_help(message)
                master_start(message)
                return
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(strings.btn.list_chats, callback_data='list_chats_1'))
            markup.add(types.InlineKeyboardButton(strings.btn.list_blocked, callback_data='list_blocked_1'))
            markup.add(types.InlineKeyboardButton(strings.btn.set_messages, callback_data='master'))
            markup.add(types.InlineKeyboardButton(strings.btn.help, callback_data='help'))
            bot.send_message(
                master_id,
                strings.msg.menu.format(first_name=message.from_user.first_name),
                reply_markup=markup,
                parse_mode='HTML'
            )

        self.start = start_menu

        @bot.callback_query_handler(func=lambda cb: cb.data == 'menu')
        def cb_menu(cb):
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(strings.btn.list_chats, callback_data='list_chats_1'))
            markup.add(types.InlineKeyboardButton(strings.btn.list_blocked, callback_data='list_blocked_1'))
            markup.add(types.InlineKeyboardButton(strings.btn.set_messages, callback_data='master'))
            markup.add(types.InlineKeyboardButton(strings.btn.help, callback_data='help'))
            bot.edit_message_text(
                text=strings.msg.menu.format(first_name=cb.from_user.first_name),
                reply_markup=markup,
                chat_id=cb.message.chat.id,
                message_id=cb.message.message_id,
                parse_mode='HTML'
            )
            bot.answer_callback_query(cb.id, strings.ans.menu)

        @bot.message_handler(func=lambda message: message.chat.id == master_id, commands=["help"])
        def command_help(message):
            bot.send_message(
                master_id,
                strings.msg.help.format(first_name=message.from_user.first_name),
                parse_mode='HTML'
            )

        @bot.callback_query_handler(func=lambda cb: cb.data == 'help')
        def cb_help(cb):
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(strings.btn.back, callback_data='menu'))
            bot.edit_message_text(
                text=strings.msg.help.format(first_name=cb.from_user.first_name),
                reply_markup=markup,
                chat_id=cb.message.chat.id,
                message_id=cb.message.message_id,
                parse_mode='HTML'
            )
            bot.answer_callback_query(cb.id, strings.ans.help)

        @bot.message_handler(func=lambda message: message.chat.id == master_id, commands=['messages'])
        def master_start(_):
            db.common.state = 'set_start'
            self.send_state()

        @bot.callback_query_handler(func=lambda cb: cb.data == 'master')
        def master_cb(cb):
            bot.edit_message_text(
                strings.msg.master_intro,
                reply_markup=None,
                chat_id=cb.message.chat.id,
                message_id=cb.message.message_id,
                parse_mode='HTML'
            )
            db.common.state = 'set_start'
            self.send_state()

        @bot.message_handler(func=lambda m: m.chat.id == master_id and db.common.state.startswith('set'))
        def master_step(message):
            if message.content_type == 'text':
                msg_type = db.common.state.split('_')[1]
                old_msg = db.common.messages.get(msg_type)
                new_msg = str(message.text)
                db.common.messages[msg_type] = new_msg  # save to db
                db.common.save()
                prev_step_msg = db.common.prev_msg

                # edit previous
                if old_msg:
                    text = strings.msg.master_edited.format(
                        msg_type=msg_type,
                        old_msg=old_msg,
                        new_msg=new_msg
                    )
                else:
                    text = strings.msg.master_set.format(
                        msg_type=msg_type,
                        new_msg=new_msg
                    )

                bot.edit_message_text(
                    text,
                    chat_id=prev_step_msg.chat.id,
                    message_id=prev_step_msg.message_id,
                    reply_markup=None,
                    parse_mode='HTML'
                )

                # set state
                db.common.state = {
                    'set_start': 'set_unavailable',
                    'set_unavailable': 'set_block',
                    'set_block': 'none'
                }[db.common.state]

                self.send_state()
            else:
                bot.reply_to(message, strings.msg.invalid_content_type)

        @bot.callback_query_handler(func=lambda cb: cb.data == 'skip')
        def master_skip(cb):
            if cb.message.message_id == db.common.prev_msg.message_id:
                msg_type = db.common.state.split('_')[1]
                old_msg = db.common.messages.get(msg_type)
                bot.edit_message_text(
                    strings.msg.master_skipped.format(
                        msg_type=msg_type,
                        msg=old_msg
                    ),
                    chat_id=cb.message.chat.id,
                    message_id=cb.message.message_id,
                    reply_markup=None,
                    parse_mode='HTML'
                )

                # set state
                db.common.state = {
                    'set_start': 'set_unavailable',
                    'set_unavailable': 'set_block',
                    'set_block': 'none'
                }[db.common.state]

                self.send_state()
                bot.answer_callback_query(cb.id, strings.ans.skipped)
            else:
                bot.answer_callback_query(cb.id, strings.ans.error)

        @bot.callback_query_handler(func=lambda cb: cb.data == 'back')
        def master_back(cb):
            if cb.message.message_id == db.common.prev_msg.message_id:
                msg_type = db.common.state.split('_')[1]
                old_msg = db.common.messages.get(msg_type)
                bot.edit_message_text(
                    strings.msg.master_skipped.format(
                        msg_type=msg_type,
                        msg=old_msg
                    ),
                    chat_id=cb.message.chat.id,
                    message_id=cb.message.message_id,
                    reply_markup=None,
                    parse_mode='HTML'
                )

                # set state
                db.common.state = {
                    'set_unavailable': 'set_start',
                    'set_block': 'set_unavailable'
                }[db.common.state]

                self.send_state()
                bot.answer_callback_query(cb.id, strings.ans.returned)
            else:
                bot.answer_callback_query(cb.id, strings.ans.error)

        # handles inline keyboard buttons under the chats list
        @bot.callback_query_handler(func=lambda cb: cb.data.startswith('list_blocked_'))
        def blocked_list_pages(cb):
            page_no = int(cb.data.replace('list_blocked_', '', 1))
            pages_count, chats = db.chat.get_blocked_page(page_no)
            markup = types.InlineKeyboardMarkup()
            if chats:
                s = strings.msg.blockedlist_header
                for index, chat in enumerate(chats):
                    s += "<code>{index}.</code> {chat:html}\n".format(index=index, chat=chat)
                    markup.add(
                        types.InlineKeyboardButton(
                            "{index}. {chat:btn}".format(index=index, chat=chat),
                            callback_data='chat_show_{}'.format(chat.id)
                        )
                    )
            else:
                s = strings.msg.none_blocked
            if pages_count > 1:
                markup.row(*pager_buttons('list_blocked_', page_no, pages_count))
            markup.add(types.InlineKeyboardButton(strings.btn.menu, callback_data='menu'))
            bot.edit_message_text(
                s,
                parse_mode='HTML',
                reply_markup=markup,
                message_id=cb.message.message_id,
                chat_id=cb.from_user.id
            )
            bot.answer_callback_query(cb.id, strings.ans.done)

        # handles inline keyboard buttons under the chats list
        @bot.callback_query_handler(func=lambda cb: cb.data.startswith('list_chats_'))
        def chat_list_pages(cb):
            page_no = int(cb.data.replace('list_chats_', '', 1))
            pages_count, chats = db.chat.get_page(page_no)
            markup = types.InlineKeyboardMarkup()
            if chats:
                s = strings.msg.chatlist_header
                for index, chat in enumerate(chats):
                    s += "<code>{index}.</code> {chat:html}\n".format(index=index, chat=chat)
                    markup.add(
                        types.InlineKeyboardButton(
                            "{index}. {chat:btn}".format(index=index, chat=chat),
                            callback_data='chat_show_{}'.format(chat.id)
                        )
                    )
            else:
                s = strings.msg.no_chats
            if pages_count > 1:
                markup.row(*pager_buttons('list_chats_', page_no, pages_count))
            markup.add(types.InlineKeyboardButton(strings.btn.menu, callback_data='menu'))
            bot.edit_message_text(
                s,
                parse_mode='HTML',
                reply_markup=markup,
                message_id=cb.message.message_id,
                chat_id=cb.from_user.id
            )
            bot.answer_callback_query(cb.id, strings.ans.done)

        # handles inline keyboard buttons under the chat_view
        @bot.callback_query_handler(func=lambda cb: cb.data.startswith('chat'))
        def chat_block_toggle(cb):
            command, _id = cb.data.split('_')[1:]
            chat = db.chat.get_by_id(int(_id))  # gets chat info from db
            assert chat  # makes sure that chat is in db

            if command == 'block':  # block command
                chat.blocked = True
                bot.answer_callback_query(cb.id, strings.ans.blocked)
            elif command == 'unblock':  # unblock command
                chat.blocked = False
                bot.answer_callback_query(cb.id, strings.ans.unblocked)
            else:
                bot.answer_callback_query(cb.id, strings.ans.done)

            text, markup = get_chatview_markup(chat)  # edits message according to update
            bot.edit_message_text(
                text,
                parse_mode='HTML',
                reply_markup=markup,
                message_id=cb.message.message_id,
                chat_id=cb.from_user.id
            )

            db.chat.update(chat)  # pushes changes to db

        @bot.callback_query_handler(func=lambda cb: cb.data.startswith('log'))
        def show_log(cb):
            chat_id, page_no = cb.data.split('_')[1:]
            chat_id = int(chat_id)
            page_no = int(page_no)

            chat = db.chat.get_by_id(chat_id)  # gets chat info from db

            text, markup = get_chatview_markup(chat, page_no)

            bot.edit_message_text(
                text,
                parse_mode='HTML',
                reply_markup=markup,
                message_id=cb.message.message_id,
                chat_id=cb.from_user.id
            )
            bot.answer_callback_query(cb.id, strings.ans.done)

        # a set of commands for admin to view special messages
        @my_commandset_handler('msg')
        def show_msg(message):
            bot.send_chat_action(message.from_user.id, action="typing")
            m_id = message.text.replace('/msg', '', 1).split()[0]
            old_msg = db.msg.get_by_shortid(m_id)
            bot.forward_message(master_id, old_msg.chat.id, old_msg.message_id)

        # Handle always first "/start" message when new chat with your bot is created (for users other than admin)
        @bot.message_handler(func=lambda message: message.chat.id != master_id, commands=["start"])
        def command_start_all(message):
            bot.send_message(
                message.chat.id,
                db.common.startmsg.format(name=message.from_user.first_name)
            )

        # Handle the messages which are not sent by the admin user(the one who is handling the bot)
        # Sends texts, audios, document etc to the admin
        @bot.message_handler(
            func=lambda message: message.chat.id != master_id,
            content_types=['text', 'audio', 'document', 'photo', 'sticker', 'video', 'voice', 'location', 'contact']
        )
        def handle_all(message):
            chat = db.chat.get_by_id(message.chat.id)  # get chat from database
            if not chat:  # If chat is new
                chat = message.chat
            else:
                chat.update(message.chat)  # updates chat data
            db.chat.update(chat)  # pushes updated data back to db

            # checks whether the admin has blocked that chat via bot or not
            if chat.blocked:
                if chat.type == 'private':
                    # if blocked: notify user about it
                    bot.send_message(message.chat.id, db.common.blockmsg)
                else:
                    bot.leave_chat(chat.id)

            else:
                # if not blocked:
                db.msg.create(message)  # log message in db

                text = strings.msg.new_msg.format(chat=chat, message=message)
                markup = types.InlineKeyboardMarkup()
                markup.add(
                    types.InlineKeyboardButton(strings.btn.show_log, callback_data='log_{}_0'.format(chat.id)),
                    types.InlineKeyboardButton(strings.btn.block, callback_data='chat_block_{}'.format(chat.id)),
                    types.InlineKeyboardButton(strings.btn.reply, callback_data='reply_{}'.format(chat.id))
                )
                markup.add(types.InlineKeyboardButton(strings.btn.menu, callback_data='menu'))
                bot.send_message(  # send it to admin
                    master_id,
                    text,
                    parse_mode='HTML',
                    reply_markup=markup
                )

                if message.content_type != 'text':
                    bot.forward_message(master_id, message.chat.id, message.message_id)

                # check the status of the admin whether he's available or not
                if db.common.availability == 'unavailable' and chat.type == 'private':
                    # and notify user if unavailable
                    bot.send_message(message.chat.id, db.common.nonavailmsg)

        @bot.callback_query_handler(func=lambda cb: cb.data.startswith('reply_'))
        def reply_to(cb):
            db.common.replying_to = int(cb.data.replace('reply_', '', 1))
            bot.register_next_step_handler(cb.message, send_reply)
            bot.answer_callback_query(cb.id, strings.ans.reply)

        # handles admin's replies
        def send_reply(message):
            if db.common.replying_to:
                chat_id = db.common.replying_to
            else:
                bot.send_message(master_id, strings.msg.noone_to_reply)
                return

            if message.content_type == 'text':
                bot.send_chat_action(chat_id, action='typing')
                sent_msg = bot.send_message(chat_id, message.text)
            elif message.content_type == "sticker":
                bot.send_chat_action(chat_id, action='typing')
                sent_msg = bot.send_sticker(chat_id, message.sticker.file_id)
            elif message.content_type == "photo":
                bot.send_chat_action(chat_id, action='upload_photo')
                sent_msg = bot.send_photo(chat_id, list(message.photo)[-1].file_id)
            elif message.content_type == "voice":
                bot.send_chat_action(chat_id, action='record_audio')
                sent_msg = bot.send_voice(chat_id, message.voice.file_id, duration=message.voice.duration)
            elif message.content_type == "document":
                bot.send_chat_action(chat_id, action='upload_document')
                sent_msg = bot.send_document(chat_id, data=message.document.file_id)
            elif message.content_type == "audio":
                bot.send_chat_action(chat_id, action='upload_audio')
                sent_msg = bot.send_audio(
                    chat_id,
                    performer=message.audio.performer,
                    audio=message.audio.file_id,
                    title=message.audio.title,
                    duration=message.audio.duration
                )
            elif message.content_type == "video":
                bot.send_chat_action(chat_id, action='upload_video')
                sent_msg = bot.send_video(chat_id, data=message.video.file_id, duration=message.video.duration)
            elif message.content_type == "location":
                # No Google Maps on my phone, so this code is untested, should work fine though
                bot.send_chat_action(chat_id, action='find_location')
                sent_msg = bot.send_location(
                    chat_id,
                    latitude=message.location.latitude,
                    longitude=message.location.longitude
                )
            else:
                sent_msg = bot.send_message(master_id, strings.msg.invalid_content_type)

            db.msg.create(sent_msg)  # log message in db
            db.common.update_last_seen()

        print('@{} has started for {}'.format(self.username, self.master_id))
        bot.send_message(master_id, strings.msg.bot_started)

    def send_state(self):
        db = self.db
        if db.common.state.startswith('set'):
            msg_type = db.common.state.split('_')[1]
            markup = types.InlineKeyboardMarkup()
            buttons = list()
            if msg_type != 'start':
                buttons.append(types.InlineKeyboardButton(strings.btn.back, callback_data='back'))
            elif db.common.messages:
                buttons.append(types.InlineKeyboardButton(strings.btn.back, callback_data='menu'))

            text = strings.msg.master_step_descr[msg_type]
            if db.common.messages.get(msg_type):
                text += strings.msg.master_step.format(
                    msg_type=msg_type,
                    msg=db.common.messages[msg_type]
                )
                buttons.append(types.InlineKeyboardButton(strings.btn.skip, callback_data='skip'))
            else:
                text += strings.msg.master_notset.format(msg_type=msg_type)

            markup.add(*buttons)
            db.common.prev_msg = bot.send_message(
                self.master_id,
                text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        else:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(strings.btn.menu, callback_data='menu'))
            bot.send_message(
                self.master_id,
                strings.msg.master_done,
                reply_markup=markup,
                parse_mode='HTML'
            )
            db.common.prev_msg = None

    def start(self):
        self.send_message(
            self.master_id,
            strings.msg.help.format(first_name='Master'),
            parse_mode='HTML'
        )
        self.db.common.state = 'set_start'
        self.send_state()

if __name__ == '__main__':
    bot = ProxyBot(config.token, config.my_id)
    bot.polling(none_stop=True)
