import logging

import certifi
import urllib3
from ask_sdk_core.skill_builder import SkillBuilder
from ask_sdk_core.dispatch_components import AbstractRequestHandler
from ask_sdk_core.dispatch_components import AbstractExceptionHandler
import ask_sdk_core.utils as ask_utils
from ask_sdk_core.handler_input import HandlerInput

from ask_sdk_model import Response
import os
import openai

# OPEN AI Config
openai.organization = os.getenv("OPENAI_API_ORG")
openai.api_key = os.getenv("OPENAI_API_KEY")
model = os.getenv("MODEL", "text-davinci-003")
temperature = float(os.getenv("TEMPERATURE", 0.1))
max_tokens = int(os.getenv("MAX_TOKENS", 3000))

# SLACK CONFIG
slack_url = os.getenv("SLACK_URL")
channel = os.getenv("SLACK_CHANNEL", "#chatgpt")

logger = logging.getLogger(__name__)
logger.setLevel(os.getenv("LOGLEVEL", logging.DEBUG))

RE_PROMPT = "Do you have any other questions?"


class LaunchRequestHandler(AbstractRequestHandler):
    """Handler for Skill Launch."""

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return ask_utils.is_request_type("LaunchRequest")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        speak_output = "ChatGPT here"
        return handler_input.response_builder.speak(speak_output).ask(speak_output).response


class ChatGPTIntentHandler(AbstractRequestHandler):
    """Handler for ChatGPTIntent. Must be evaluated after Slack Intent"""

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return ask_utils.get_intent_name(handler_input).startswith("ChatGPT")

    def handle(self, handler_input: HandlerInput) -> Response:
        question = get_question(handler_input)
        logger.debug(question)
        speak_output = openai.Completion.create(
            model=model,
            prompt=question,
            max_tokens=max_tokens,
            temperature=temperature
        ).choices[0].text

        return handler_input.response_builder.speak(speak_output) \
            .ask(RE_PROMPT) \
            .set_should_end_session(False).response


def get_question(handler_input: HandlerInput) -> str:
    request = handler_input.request_envelope.request
    # Hack to capture the first trigger word by extracting from the intent name
    # Example ChatGPTDefineIntent will return Define below which is the initial trigger for this request
    first_word = ask_utils.get_intent_name(handler_input).split("ChatGPT")[1][:-6]
    return first_word + " " + request.intent.slots["question"].value


class ImageHandler(AbstractRequestHandler):
    """Handler for ImageHandler."""

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return ask_utils.is_intent_name("ImageHandler")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        question = handler_input.request_envelope.request.intent.slots["question"].value

        image_url = openai.Image.create(
            prompt=question,
            n=1,
            size="1024x1024",
            response_format="url"
        ).data[0]["url"]

        res = send_slack_message(question=question, image_url=image_url)
        return handler_input.response_builder.speak(f"{res} sending to slack") \
            .ask(RE_PROMPT) \
            .set_should_end_session(False).response


class ChatGPTSlackHandler(AbstractRequestHandler):
    """Handler for ChatGPTSlackHandler."""

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return ask_utils.is_intent_name("ChatGPTSlackHandler")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        question = handler_input.request_envelope.request.intent.slots["question"].value
        # Remove the first word here as it likely matches a persons name e.g. 'Slack me', 'Message Joe ...'
        question_without_first_word = " ".join(question.split(" ")[1:])
        chatgpt_output = openai.Completion.create(
            model=model,
            prompt=question_without_first_word,
            max_tokens=max_tokens,
            temperature=temperature
        ).choices[0].text

        res = send_slack_message(question=question_without_first_word, response=chatgpt_output)
        return handler_input.response_builder.speak(f"{res} sending to slack") \
            .ask(RE_PROMPT).set_should_end_session(False).response


def send_slack_message(question, response=None, image_url=None) -> str:
    data = {
        "channel": channel,
        "blocks": [
            {
                "type": "header", "text": {"type": "plain_text", "text": question.capitalize()}
            },
            {
                "type": "divider"
            }
        ]
    }

    if response:
        data["blocks"].append({"type": "section", "text": {"type": "mrkdwn", "text": response}})

    if image_url:
        data["blocks"].append({
            "type": "image",
            "image_url": image_url,
            "alt_text": question.capitalize()
        })

        http = urllib3.PoolManager(
            cert_reqs="CERT_REQUIRED",
            ca_certs=certifi.where()
        )

        resp = http.request("POST", slack_url, json=data, headers={"Content-Type": "application/json"})

        if resp.status != 200:
            logger.error(resp.status, resp.data)
            return "failed"
    return "success"


class HelpIntentHandler(AbstractRequestHandler):
    """Handler for Help Intent."""

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return ask_utils.is_intent_name("AMAZON.HelpIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        speak_output = "You can say hello to me! How can I help?"
        return handler_input.response_builder.speak(speak_output).ask(speak_output).response


class CancelOrStopIntentHandler(AbstractRequestHandler):
    """Single handler for Cancel and Stop Intent."""

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return ask_utils.get_intent_name(handler_input) in ["AMAZON.StopIntent", "AMAZON.CancelIntent"]

    def handle(self, handler_input: HandlerInput) -> Response:
        return handler_input.response_builder.speak("Goodbye!").response


class SessionEndedRequestHandler(AbstractRequestHandler):
    """Handler for Session End."""

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return ask_utils.is_request_type("SessionEndedRequest")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        # Any cleanup logic goes here.
        return handler_input.response_builder.response


class IntentReflectorHandler(AbstractRequestHandler):
    """The intent reflector is used for interaction model testing and debugging.
    It will simply repeat the intent the user said. You can create custom handlers
    for your intents by defining them above, then also adding them to the request
    handler chain below.
    """

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return ask_utils.is_request_type("IntentRequest")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        intent_name = ask_utils.get_intent_name(handler_input)
        speak_output = "You just triggered " + intent_name + "."
        return handler_input.response_builder.speak(speak_output).response


class CatchAllExceptionHandler(AbstractExceptionHandler):
    """Generic error handling to capture any syntax or routing errors. If you receive an error
    stating the request handler chain is not found, you have not implemented a handler for
    the intent being invoked or included it in the skill builder below.
    """

    def can_handle(self, handler_input: HandlerInput, exception: Exception) -> bool:
        return True

    def handle(self, handler_input: HandlerInput, exception: Exception) -> Response:
        logger.error(exception, exc_info=True)
        speak_output = "Sorry, I had trouble doing what you asked. Please try again."

        return handler_input.response_builder.speak(speak_output).ask(speak_output).response


# The SkillBuilder object acts as the entry point for your skill, routing all request and response
# payloads to the handlers above. Make sure any new handlers or interceptors you've
# defined are included below. The order matters - they're processed top to bottom.

sb = SkillBuilder()
sb.add_request_handler(LaunchRequestHandler())
sb.add_request_handler(ChatGPTSlackHandler())
sb.add_request_handler(ImageHandler())
sb.add_request_handler(ChatGPTIntentHandler())
sb.add_request_handler(HelpIntentHandler())
sb.add_request_handler(CancelOrStopIntentHandler())
sb.add_request_handler(SessionEndedRequestHandler())
# make sure IntentReflectorHandler is last so it doesn't override your custom intent handlers
sb.add_request_handler(IntentReflectorHandler())

sb.add_exception_handler(CatchAllExceptionHandler())
handler = sb.lambda_handler()
