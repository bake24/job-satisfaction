from aiogram.fsm.state import State, StatesGroup


class SurveyStates(StatesGroup):
    choosing_language = State()
    waiting_unit = State()
    waiting_driver_selection = State()
    waiting_driver_confirm = State()
    waiting_department_contact = State()
    waiting_department_question = State()
    waiting_dispatcher_rating = State()
    waiting_department_feedback_decision = State()
    waiting_department_feedback_text = State()
