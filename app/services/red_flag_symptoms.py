"""Curated "red flag" symptom categories, reviewed with a healthcare
professional as part of the product's clinical-triage design work.

These are symptoms that are, by themselves, signs of a potentially serious
condition regardless of how many times they've occurred (as opposed to the
recurring-pattern rules in app/bot/scheduler.py, where severity comes from
persistence, not from any single symptom). RedFlagDetectionService only
ever classifies a description into one of these categories -- it never
invents a category outside this list.

This list is a clinical decision, not an engineering one: changing it
needs the same kind of review it got the first time, not just a code
change.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RedFlagCategory:
    key: str
    label: str
    # Lay-language examples used to steer the classifier prompt -- not an
    # exhaustive keyword list, the model is expected to generalize beyond
    # these exact phrases.
    example_phrases: tuple[str, ...]


RED_FLAG_ABSOLUTE_CATEGORIES: tuple[RedFlagCategory, ...] = (
    RedFlagCategory(
        key="cardiorrespiratorio",
        label="Sinais cardiorrespiratórios",
        example_phrases=(
            "não consigo respirar direito",
            "estou ficando sem ar",
            "não consigo puxar o ar",
            "estou sufocando",
            "aperto forte no peito",
            "peso no peito",
            "dor no peito que não passa",
            "dor no peito com suor frio",
            "desmaiei e não sei por quê",
            "coração disparado e quase desmaiando",
            "muito pálido e suando frio de repente",
        ),
    ),
    RedFlagCategory(
        key="neurologico",
        label="Sinais neurológicos súbitos",
        example_phrases=(
            "minha boca entortou",
            "um lado do rosto caiu",
            "meu braço não responde",
            "não consigo levantar um braço",
            "minha perna não obedece",
            "estou falando enrolado",
            "não consigo encontrar as palavras",
            "não estou entendendo o que falam comigo",
            "perdi a visão de repente",
            "estou vendo dobrado",
            "perdi o equilíbrio do nada",
            "dor de cabeça muito forte que começou de repente",
            "fiquei confuso de repente",
            "tive uma convulsão",
        ),
    ),
    RedFlagCategory(
        key="consciencia",
        label="Alteração de consciência",
        example_phrases=(
            "a pessoa não responde quando chamo",
            "não consigo ficar em pé, estou quase apagando",
            "respirando estranho e não responde",
        ),
    ),
    RedFlagCategory(
        key="sangramento_trauma_intoxicacao",
        label="Sangramento, trauma ou intoxicação",
        example_phrases=(
            "sangramento que não para",
            "vomitei sangue",
            "sangue nas fezes",
            "tomei a dose errada do remédio e estou passando mal",
            "engoli algo que pode ser veneno",
            "bati a cabeça forte e fiquei confuso",
            "queimadura grande",
            "levei um choque elétrico forte",
        ),
    ),
)

RED_FLAG_CATEGORY_BY_KEY: dict[str, RedFlagCategory] = {
    category.key: category for category in RED_FLAG_ABSOLUTE_CATEGORIES
}

# Sent to the patient (WhatsApp reply and in-app notification) whenever a
# description matches one of the categories above. Deliberately covers both
# "this is happening right now" and "this already happened and passed"
# in the same message, rather than trying to infer tense from free text --
# getting that inference wrong in the direction of "it already passed, so
# it's less urgent" is the one failure mode this can't afford, since some
# of these categories (e.g. neurologico) stay urgent even once resolved.
RED_FLAG_SAFETY_MESSAGE_PT_BR = (
    "O que você descreveu pode ser sinal de uma condição que precisa de avaliação "
    "médica urgente. Se isso está acontecendo agora, está piorando ou foi um sintoma "
    "súbito importante, procure atendimento de emergência imediatamente ou ligue para "
    "o SAMU (192). Mesmo que o sintoma já tenha passado, alguns sinais precisam ser "
    "avaliados com urgência."
)
