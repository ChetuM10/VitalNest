"""Greetings, thanks and goodbyes get a friendly fixed reply instead of a 'not enough information' answer."""
import pytest

from app.chat.small_talk import SmallTalk, detect_small_talk
from app.safety import messages

GREETINGS = [
    "Hi", "hi!", "HI", "Hello", "hello there", "Hey", "Hey there!", "Howdy", "Good morning", "good Morning!", "Good afternoon", "Good evening!",
    "Hello, how are you?", "hi how are you doing today", "How are you?", "how are you doing", "How r u", "hru", "Hi VitalNest", "  HELLO  ",
    "What's up", "what’s up?", "Whats up!", "wassup", "sup", "What is up?", "Hey, what's up?", "hey there, how's it going?", "How's it going?",
    "Hiya", "yo", "Greetings", "good day", "morning", "Hi everyone",
    "heyyy", "hiii", "Hellooo!", "HEY!!!", "hi...", "hello?!", "Hi 👋", "hey :)", "Hello 😊",
    "good morning, how are you?", "Hello! What's up?",
]
HELP = ["help", "Help!", "What can you do?", "who are you", "What are you?", "what do you do"]
THANKS = [
    "thanks", "Thanks!", "Thank you!", "thank you so much", "Thanks a lot", "Thanks a lot!!", "thx", "ty", "cheers", "Thanks VitalNest", "thank u",
    "Appreciate it", "I appreciate it", "I really appreciate it", "much appreciated", "Many thanks", "thanks so much", "Thank you very much",
    "thankyou", "thank-you", "thanx", "thankss", "OK thanks", "great, thanks!", "Thanks again", "thanks for the help", "Thank you for your answer",
]
GOODBYES = [
    "bye", "Bye!", "BYE", "byeee", "bye bye", "Goodbye", "goodbye!", "See you", "see you later", "see you soon", "See ya", "see ya later",
    "Take care", "take care!", "Catch you later", "catch you later!", "Catch ya later", "talk to you later", "ttyl", "later", "cya",
    "good night", "Goodnight!", "have a good day", "Have a great day!", "farewell", "so long", "thanks, bye", "thank you, goodbye!", "ok bye for now",
]

# Real questions that start or end with small-talk words: they must go through the normal pipeline.
NOT_SMALL_TALK = [
    "Hey, what are asthma symptoms?",
    "hi what is asthma",
    "Hello, can you tell me about diabetes?",
    "Good morning, what helps with migraines?",
    "hey what's up with my headaches",
    "what's up with my blood pressure",
    "what is up with my knee",
    "hello I have chest pain",
    "thanks, but how is it treated?",
    "Thanks! What about diabetes?",
    "appreciate it, how is asthma treated?",
    "thank you, what are the symptoms of stroke",
    "bye, one more question: what is a stroke",
    "bye bye diabetes what causes it",
    "see you at the clinic, what should I ask?",
    "take care of a burn how",
    "later today my chest hurts",
    "catch you later but first, what is asthma",
    "how are you different from a doctor",
    "how are you able to find sources",
    "morning sickness remedies",
    "good night sweats causes",
    "hi my name is Sam and I want to know about migraines",
    "What is asthma?",
    "Tell me about diabetes",
    "",
    "   ",
    "😊",
    "!!!",
]


@pytest.mark.parametrize("text", GREETINGS + HELP)
def test_greetings_and_help_requests_get_the_introduction(text):
    result = detect_small_talk(text)
    assert isinstance(result, SmallTalk), text
    assert result.reply == messages.GREETING_MESSAGE


@pytest.mark.parametrize("text", THANKS)
def test_thanks_gets_a_you_are_welcome(text):
    result = detect_small_talk(text)
    assert result is not None, text
    assert result.reply == messages.THANKS_MESSAGE


@pytest.mark.parametrize("text", GOODBYES)
def test_goodbyes_get_a_goodbye(text):
    result = detect_small_talk(text)
    assert result is not None, text
    assert result.reply == messages.GOODBYE_MESSAGE


@pytest.mark.parametrize("text", NOT_SMALL_TALK)
def test_real_questions_are_never_treated_as_small_talk(text):
    assert detect_small_talk(text) is None, text


def test_the_replies_are_friendly_and_say_what_the_assistant_is_for():
    assert "health" in messages.GREETING_MESSAGE.lower()
    assert "MedlinePlus" in messages.GREETING_MESSAGE
    assert "personal health details" in messages.GREETING_MESSAGE
    assert "welcome" in messages.THANKS_MESSAGE.lower()
    assert "emergency" in messages.GOODBYE_MESSAGE.lower()


def test_each_category_gets_its_own_reply():
    assert len({messages.GREETING_MESSAGE, messages.THANKS_MESSAGE, messages.GOODBYE_MESSAGE}) == 3
