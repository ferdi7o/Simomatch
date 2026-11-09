"""Small logcat milestones; no GL calls, renderer changes or user data."""
from threading import current_thread, get_ident
from kivy.logger import Logger


def milestone(event, **details):
    fields = ' '.join(f'{key}={value}' for key, value in details.items())
    Logger.info(f'SimomatchDiag: {event} thread={current_thread().name} ident={get_ident()} {fields}')
