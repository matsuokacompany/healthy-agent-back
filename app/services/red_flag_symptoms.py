"""Curated "red flag" symptom categories, reviewed with a healthcare
professional as part of the product's clinical-triage design work.

Two tiers, both reviewed together but meaning different things:

- ABSOLUTE: symptoms that are, by themselves, signs of a potentially
  serious condition regardless of patient history or how many times
  they've occurred (cardiorrespiratory, neurological, altered
  consciousness, bleeding/trauma/poisoning).
- CONTEXTUAL: symptoms that are NOT inherently alarming on their own, but
  become red-flag-worthy given a specific item in the patient's risk
  factor history (see ANAMNESE_RISK_FACTORS / CONTEXTUAL_RISK_RULES below)
  -- e.g. mild shortness of breath is routine on its own, but warrants the
  same urgency as an absolute red flag in a patient with a recent surgery
  or a history of thrombosis.

RedFlagDetectionService only ever classifies a description into one of
these categories -- it never invents a category outside this list. This
list (and the risk-factor rules) is a clinical decision, not an
engineering one: changing it needs the same kind of review it got the
first time, not just a code change.
"""

from dataclasses import dataclass
from typing import Literal

RedFlagTier = Literal["absoluto", "contextual"]


@dataclass(frozen=True)
class RedFlagCategory:
    key: str
    label: str
    tier: RedFlagTier
    # Lay-language examples used to steer the classifier prompt -- not an
    # exhaustive keyword list, the model is expected to generalize beyond
    # these exact phrases.
    example_phrases: tuple[str, ...]


RED_FLAG_ABSOLUTE_CATEGORIES: tuple[RedFlagCategory, ...] = (
    RedFlagCategory(
        key="cardiorrespiratorio",
        label="Sinais cardiorrespiratórios",
        tier="absoluto",
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
        tier="absoluto",
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
        tier="absoluto",
        example_phrases=(
            "a pessoa não responde quando chamo",
            "não consigo ficar em pé, estou quase apagando",
            "respirando estranho e não responde",
        ),
    ),
    RedFlagCategory(
        key="sangramento_trauma_intoxicacao",
        label="Sangramento, trauma ou intoxicação",
        tier="absoluto",
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

# Not alarming on their own -- only escalated when the patient's anamnese
# has a matching risk factor (see CONTEXTUAL_RISK_RULES).
RED_FLAG_CONTEXTUAL_CATEGORIES: tuple[RedFlagCategory, ...] = (
    RedFlagCategory(
        key="falta_de_ar_leve",
        label="Falta de ar leve ou moderada",
        tier="contextual",
        example_phrases=(
            "uma falta de ar leve",
            "fiquei um pouco sem ar",
            "cansei mais do que o normal",
            "um chiado no peito",
            "um pouco de dificuldade pra respirar",
        ),
    ),
    RedFlagCategory(
        key="dor_abdominal",
        label="Dor abdominal",
        tier="contextual",
        example_phrases=(
            "dor na barriga",
            "dor abdominal",
            "cólica forte",
            "dor na região do estômago",
        ),
    ),
    RedFlagCategory(
        key="febre",
        label="Febre",
        tier="contextual",
        example_phrases=(
            "estou com febre",
            "febre alta",
            "febre e calafrio",
        ),
    ),
    RedFlagCategory(
        key="inchaco_ou_dor_em_uma_perna",
        label="Inchaço ou dor em uma perna",
        tier="contextual",
        example_phrases=(
            "minha perna inchou",
            "dor e inchaço numa perna só",
            "uma perna ficou quente e vermelha",
        ),
    ),
    RedFlagCategory(
        key="palpitacao",
        label="Palpitação",
        tier="contextual",
        example_phrases=(
            "meu coração está acelerado",
            "senti o coração bater forte",
            "palpitação",
        ),
    ),
    RedFlagCategory(
        key="mal_estar_confusao_leve",
        label="Mal-estar, fraqueza, suor ou tremor súbitos",
        tier="contextual",
        example_phrases=(
            "fiquei fraco e suando do nada",
            "tremendo e confuso",
            "mal-estar súbito",
        ),
    ),
    RedFlagCategory(
        key="sinais_de_descompensacao_cardiaca",
        label="Piora ao deitar, inchaço ou ganho rápido de peso",
        tier="contextual",
        example_phrases=(
            "piora quando eu deito",
            "as pernas incharam",
            "ganhei peso rápido essa semana",
        ),
    ),
    RedFlagCategory(
        key="sangramento_leve",
        label="Sangramento leve",
        tier="contextual",
        example_phrases=(
            "um sangramento pequeno",
            "sangrou um pouco",
            "hematoma que apareceu sozinho",
        ),
    ),
    RedFlagCategory(
        key="dor_de_cabeca_com_alteracao_visual",
        label="Dor de cabeça com alteração visual",
        tier="contextual",
        example_phrases=(
            "dor de cabeça e visão embaçada",
            "dor de cabeça com vista escura",
        ),
    ),
)

RED_FLAG_ALL_CATEGORIES: tuple[RedFlagCategory, ...] = RED_FLAG_ABSOLUTE_CATEGORIES + RED_FLAG_CONTEXTUAL_CATEGORIES
RED_FLAG_CATEGORY_BY_KEY: dict[str, RedFlagCategory] = {category.key: category for category in RED_FLAG_ALL_CATEGORIES}

# The reviewed risk-factor checklist -- field name on Anamnese -> PT-BR
# label shown in the anamnese form. Single source of truth for the model
# columns (app/models/models.py), the API schema (app/models/schemas.py)
# and the rule table below; keep all three in sync with this tuple.
ANAMNESE_RISK_FACTORS: tuple[tuple[str, str], ...] = (
    ("risk_heart_disease", "Doença cardíaca"),
    ("risk_prior_heart_attack", "Infarto prévio"),
    ("risk_prior_stroke_or_tia", "AVC ou AIT (derrame) prévio"),
    ("risk_asthma_or_copd", "Asma ou DPOC"),
    ("risk_heart_failure", "Insuficiência cardíaca"),
    ("risk_diabetes", "Diabetes"),
    ("risk_anticoagulant_use", "Uso de anticoagulante"),
    ("risk_immunosuppression", "Imunossupressão"),
    ("risk_pregnancy_or_postpartum", "Gravidez ou pós-parto"),
    ("risk_active_cancer", "Câncer ativo"),
    ("risk_prior_thrombosis_or_embolism", "Histórico de trombose ou embolia"),
    ("risk_recent_surgery_or_immobilization", "Cirurgia recente ou imobilização prolongada"),
    ("risk_epilepsy", "Epilepsia"),
)
ANAMNESE_RISK_FACTOR_FIELDS: tuple[str, ...] = tuple(field for field, _label in ANAMNESE_RISK_FACTORS)
ANAMNESE_RISK_FACTOR_LABELS: dict[str, str] = dict(ANAMNESE_RISK_FACTORS)

# Which CONTEXTUAL categories each risk factor elevates to red-flag
# urgency. A risk factor not listed here (risk_prior_stroke_or_tia,
# risk_epilepsy) has no CONTEXTUAL rule because its relevant symptoms
# (any neurological change, a seizure at all) are already caught by the
# ABSOLUTE "neurologico" category regardless of history.
CONTEXTUAL_RISK_RULES: dict[str, tuple[str, ...]] = {
    "risk_heart_disease": ("falta_de_ar_leve", "palpitacao"),
    "risk_prior_heart_attack": ("falta_de_ar_leve",),
    "risk_heart_failure": ("falta_de_ar_leve", "sinais_de_descompensacao_cardiaca"),
    "risk_asthma_or_copd": ("falta_de_ar_leve",),
    "risk_diabetes": ("mal_estar_confusao_leve",),
    "risk_anticoagulant_use": ("sangramento_leve", "dor_de_cabeca_com_alteracao_visual"),
    "risk_immunosuppression": ("febre",),
    "risk_pregnancy_or_postpartum": (
        "dor_abdominal",
        "sangramento_leve",
        "falta_de_ar_leve",
        "dor_de_cabeca_com_alteracao_visual",
    ),
    "risk_active_cancer": ("falta_de_ar_leve",),
    "risk_prior_thrombosis_or_embolism": ("falta_de_ar_leve", "inchaco_ou_dor_em_uma_perna"),
    "risk_recent_surgery_or_immobilization": ("falta_de_ar_leve", "inchaco_ou_dor_em_uma_perna"),
}

# Sent to the patient (WhatsApp reply and in-app notification) whenever a
# description matches an ABSOLUTE category. Deliberately covers both
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

# Same posture as above, for a CONTEXTUAL match -- generic (doesn't name
# the specific risk factor) so it can be reused as-is in both the WhatsApp
# reply and the in-app notification without needing extra context passed
# through the bot's status-string channel. The professional-facing
# notification (built directly in Python, not through that channel) does
# name the specific risk factor -- see notify_red_flag_symptom_contextual.
RED_FLAG_CONTEXTUAL_SAFETY_MESSAGE_PT_BR = (
    "Considerando seu histórico de saúde, o que você descreveu pode ser sinal de algo "
    "que precisa de avaliação médica urgente. Se isso está acontecendo agora ou está "
    "piorando, procure atendimento de emergência imediatamente ou ligue para o SAMU "
    "(192). Mesmo que já tenha passado, vale uma avaliação rápida dado o seu histórico."
)
