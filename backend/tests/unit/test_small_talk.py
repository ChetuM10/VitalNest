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


def first(replies):
    return replies[0]


@pytest.mark.parametrize("text", GREETINGS)
def test_greetings_and_casual_talk_get_a_friendly_reply(text):
    result = detect_small_talk(text)
    assert isinstance(result, SmallTalk), text
    assert result.reply in messages.GREETING_REPLIES + messages.CASUAL_REPLIES + messages.HOW_ARE_YOU_REPLIES


@pytest.mark.parametrize("text", ["What can you do?", "who are you", "What are you?", "what do you do"])
def test_what_can_you_do_gets_the_introduction(text):
    assert detect_small_talk(text).reply == messages.GREETING_MESSAGE


@pytest.mark.parametrize("text", THANKS)
def test_thanks_gets_a_you_are_welcome(text):
    result = detect_small_talk(text)
    assert result is not None, text
    assert result.reply in messages.THANKS_REPLIES


@pytest.mark.parametrize("text", GOODBYES)
def test_goodbyes_get_a_goodbye(text):
    result = detect_small_talk(text)
    assert result is not None, text
    assert result.reply in messages.GOODBYE_REPLIES


OPENERS = [
    "I need help", "i need help.", "Need help", "I need some help", "I need your help please", "Help", "Help!", "help me", "Can you help me?",
    "can you help", "Could you help me out?", "Will you help me", "I have a question", "i have a quick question", "I've got a question",
    "I have a health question", "I have a question for you", "I want to ask a question", "I'd like to ask something", "Can I ask a question?",
    "may i ask you something", "question", "Quick question", "I'm looking for help", "I want advice", "Hey, I need help", "hi can you help me",
    "I NEED HELP!!!", "Can you help me 🙏",
]


@pytest.mark.parametrize("text", OPENERS)
def test_conversation_openers_are_welcomed_not_sent_to_search(text):
    result = detect_small_talk(text)
    assert result is not None, text
    assert result.reply in messages.OPENER_REPLIES


def test_the_opener_examples_from_the_brief():
    assert detect_small_talk("I need help", choose=first).reply == "Sure! Let me know what you need help with."
    assert detect_small_talk("Can you help me?", choose=lambda r: r[1]).reply == "Absolutely! What would you like to know?"
    assert detect_small_talk("I have a question", choose=lambda r: r[2]).reply == "Sure, go ahead. I'm listening."


def test_casual_and_how_are_you_have_their_own_replies():
    assert detect_small_talk("What's up?", choose=first).reply == "Not much! I'm here and ready to help. What's on your mind?"
    assert detect_small_talk("How are you?", choose=first).reply == "I'm doing well, thanks for asking! How can I help you today?"
    assert detect_small_talk("Hello, how are you?").reply in messages.HOW_ARE_YOU_REPLIES
    assert detect_small_talk("hey what's up").reply in messages.CASUAL_REPLIES


@pytest.mark.parametrize(
    "text, replies",
    [("Hi", messages.GREETING_REPLIES), ("What's up", messages.CASUAL_REPLIES), ("How are you?", messages.HOW_ARE_YOU_REPLIES),
     ("I need help", messages.OPENER_REPLIES), ("Thanks", messages.THANKS_REPLIES), ("Bye", messages.GOODBYE_REPLIES)],
)
def test_replies_vary_and_every_variant_can_appear(text, replies):
    assert len(replies) >= 3 and len(set(replies)) == len(replies)
    seen = {detect_small_talk(text).reply for _ in range(400)}
    assert seen == set(replies)


MIXED_AND_VAGUE_BUT_REAL = [
    "Can you help me with my headache?",
    "I need help with diabetes",
    "I need help understanding my blood pressure",
    "I have a question about asthma",
    "can I ask a question about vaccines",
    "I want advice on sleeping better",
    "Help me understand insulin",
    "Hi, I need help with asthma",
    "Thanks, but how is diabetes treated?",
    "Hey, what are asthma symptoms?",
]


@pytest.mark.parametrize("text", MIXED_AND_VAGUE_BUT_REAL)
def test_openers_that_say_what_they_want_go_to_the_normal_pipeline(text):
    assert detect_small_talk(text) is None, text


@pytest.mark.parametrize("text", NOT_SMALL_TALK)
def test_real_questions_are_never_treated_as_small_talk(text):
    assert detect_small_talk(text) is None, text


def test_the_replies_are_friendly_and_say_what_the_assistant_is_for():
    assert "health" in messages.GREETING_MESSAGE.lower()
    assert "MedlinePlus" in messages.GREETING_MESSAGE
    assert "personal health details" in messages.GREETING_MESSAGE
    assert "welcome" in messages.THANKS_MESSAGE.lower()
    assert "emergency" in messages.GOODBYE_MESSAGE.lower()


def test_each_category_gets_its_own_replies():
    groups = [messages.GREETING_REPLIES, messages.CASUAL_REPLIES, messages.HOW_ARE_YOU_REPLIES, messages.OPENER_REPLIES,
              messages.THANKS_REPLIES, messages.GOODBYE_REPLIES]
    everything = [reply for group in groups for reply in group]
    assert len(everything) == len(set(everything))
