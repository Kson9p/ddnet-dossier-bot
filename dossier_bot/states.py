from aiogram.fsm.state import State, StatesGroup


class UserFlow(StatesGroup):
    gender = State()
    nickname = State()
    description = State()
    media = State()
    confirm = State()
    support = State()


class AdminFlow(StatesGroup):
    support_reply = State()
