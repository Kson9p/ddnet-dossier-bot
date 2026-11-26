"""FSM-состояния владельца и пользовательского режима написания."""

from aiogram.fsm.state import State, StatesGroup


class OwnerReplyStates(StatesGroup):
    waiting_for_message = State()


class UserComposeStates(StatesGroup):
    waiting_for_message = State()
