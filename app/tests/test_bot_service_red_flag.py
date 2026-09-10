from app.services.bot_service import BotService
from app.services.red_flag_symptoms import RED_FLAG_SAFETY_MESSAGE_PT_BR


def test_red_flag_status_prepends_the_safety_message_to_the_diet_question():
    response = BotService()._translate("ASK_DIET_ADHERENCE_RED_FLAG")

    assert response.text.startswith(RED_FLAG_SAFETY_MESSAGE_PT_BR)
    assert "dieta" in response.text
    assert response.buttons == (("diet_yes", "Sim"), ("diet_no", "Não"))


def test_normal_status_does_not_include_the_safety_message():
    response = BotService()._translate("ASK_DIET_ADHERENCE")

    assert RED_FLAG_SAFETY_MESSAGE_PT_BR not in response.text
