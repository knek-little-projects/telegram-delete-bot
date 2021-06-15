#!/usr/bin/env python3.8
"""
Delete telegram messages at specified time unless the bot is stopped:
1. Invite the bot to a channel
2. Reply to a message with text: "delete dd.mm.yyyy hh:mm - hh:mm"
3. The message will be deleted at [dd.mm.yyyy hh:mm - hh:mm]
4. Type "clear" to cancel all jobs
5. Type "lock"/"unlock" to set a password to the "clear" command

Usage:
    bot [--token-file=FILE] [-h]

Options:
    -t --token-file=FILE    Read tg token from file [default: ./TOKEN]
"""
from telegram import Update, ForceReply
from telegram.ext import Updater, Dispatcher, CommandHandler, MessageHandler, Filters, CallbackContext
from collections import namedtuple
from docopt import docopt
import threading
import time
import datetime as dt
import logging
import re
import os

DFMT = r"%d.%m.%Y"
TFMT = r"%H:%M"
DATE_FMT = DFMT + " " + TFMT
CRON_PERIOD_SEC = 1
WAIT_BEFORE_DELETE_SYSTEM_MSG = 10

Job = namedtuple("Job", "date1 date2 chat_id message_id tag")
password = None


class DeleteQueue:
    def __init__(self):
        self._jobs = set()

    def __iter__(self):
        # wrap _jobs in additional 'set' to be able to delete jobs in iter cycle
        return iter(set(self._jobs))

    def add(self, job):
        self._jobs.add(job)

    def delete_message(self, job):
        self._jobs.discard(job)
        try:
            dispatcher.bot.delete_message(chat_id=job.chat_id, message_id=job.message_id)
        except Exception as e:
            logger.error(e)

    def remove_jobs(self):
        self._jobs.clear()


def deleting_daemon():
    while True:
        for job in delete_queue:
            if job.date1 is None or job.date2 is None:
                pass

            elif job.date1 <= dt.datetime.now() < job.date2:
                pass

            else:
                continue

            delete_queue.delete_message(job)

        time.sleep(CRON_PERIOD_SEC)


def handler(update, context):
    global password

    msg = update.effective_message
    chat_id = update.effective_chat.id
    text = msg.text.strip().lower()
    sent = None

    if text == "hey":
        sent = context.bot.send_message(
            chat_id=chat_id,
            text="Queue:\n\n" + "\n\n".join(map(str, delete_queue)),
        )

    elif text.startswith("lock "):
        if password is None:
            password = text.split()[1]
            sent = context.bot.send_message(
                chat_id=chat_id,
                text="Locked by password '%s'" % password
            )

        else:
            sent = context.bot.send_message(
                chat_id=chat_id,
                text="Error: unlock first"
            )

    elif text.startswith("unlock "):
        if password is not None:
            password2 = text.split()[1]
            if password2 == password:
                password = None
                sent = context.bot.send_message(
                    chat_id=chat_id,
                    text="Unlocked"
                )
            else:
                sent = context.bot.send_message(
                    chat_id=chat_id,
                    text="Wrong password"
                )
        else:
            sent = context.bot.send_message(
                chat_id=chat_id,
                text="Unlocked"
            )

    elif text == "clear":
        if password is not None:
            sent = context.bot.send_message(
                chat_id=chat_id,
                text="Error: unlock first"
            )

        else:
            for job in delete_queue:
                if job.tag == "system":
                    delete_queue.delete_message(job)

            delete_queue.remove_jobs()

    elif search := re.search(r"^delete (\d\d\.\d\d\.\d\d\d\d|today|tomorrow) (\d\d:\d\d)(?:-|\s)+(\d\d:\d\d)$", text):
        attached_id = msg.reply_to_message.message_id

        date, t1, t2 = search.groups()

        if date == "today":
            date = dt.datetime.now().strftime(DFMT)

        elif date == "tomorrow":
            date = (dt.datetime.now() + dt.timedelta(days=1)).strftime(DFMT)

        date1 = dt.datetime.strptime(date + " " + t1, DATE_FMT)
        date2 = dt.datetime.strptime(date + " " + t2, DATE_FMT)

        sent = context.bot.send_message(
            chat_id=chat_id,
            reply_to_message_id=attached_id,
            text="Deleting attached message at [%s .. %s]" % (date1, date2),
        )

        delete_queue.add(Job(
            date1,
            date2,
            chat_id,
            attached_id,
            None,
        ))

    else:
        return

    sys_date1 = dt.datetime.now() + dt.timedelta(seconds=WAIT_BEFORE_DELETE_SYSTEM_MSG)
    sys_date2 = sys_date1 + dt.timedelta(days=1)

    delete_queue.add(Job(
        sys_date1,
        sys_date2,
        chat_id,
        msg.message_id,
        "system"
    ))

    if sent is not None:
        delete_queue.add(Job(
            sys_date1,
            sys_date2,
            chat_id,
            sent.message_id,
            "system"
        ))


if __name__ == "__main__":
    args = docopt(__doc__)
    token_file = args["--token-file"] or "TOKEN"

    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.DEBUG)
    logger = logging.getLogger(__name__)

    with open(token_file) as token_file:
        token = token_file.read().strip()

    updater = Updater(token=token, use_context=True)
    dispatcher = updater.dispatcher
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handler))

    delete_queue = DeleteQueue()
    threading.Thread(daemon=True, target=deleting_daemon).start()

    updater.start_polling()
    updater.idle()
