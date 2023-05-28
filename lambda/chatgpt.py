import logging

import certifi
import urllib3
from ask_sdk_core.skill_builder import SkillBuilder
from ask_sdk_core.dispatch_components import AbstractRequestHandler
from ask_sdk_core.dispatch_components import AbstractExceptionHandler
import ask_sdk_core.utils as ask_utils
from ask_sdk_core.handler_input import HandlerInput

from ask_sdk_model import Response, IntentRequest
import os
import openai


openai.organization = os.getenv("OPENAI_API_ORG")
openai.api_key = os.getenv("OPENAI_API_KEY")
slack_url = os.getenv("SLACK_URL")
channel = "#chatgpt"

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class LaunchRequestHandler(AbstractRequestHandler):
    """Handler for Skill Launch."""

    def can_handle(self, handler_input):
        return ask_utils.is_request_type("LaunchRequest")(handler_input)

    def handle(self, handler_input):
        speak_output = "ChatGPT here"
        return handler_input.response_builder.speak(speak_output).ask(speak_output).response


class ChatGPTIntentHandler(AbstractRequestHandler):
    """Handler for ChatGPTIntent."""

    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("ChatGPTIntent")(handler_input)

    def handle(self, handler_input):
        question = get_question(handler_input)
        speak_output = openai.Completion.create(
            model="text-davinci-003",
            prompt=question,
            max_tokens=1000,
            temperature=0
        ).choices[0].text
        return handler_input.response_builder.speak(speak_output).ask("Do you have any other questions?").response


def get_question(handler_input):
    request = handler_input.request_envelope.request
    return request.intent.slots["question"].value


class ChatGPTSlackHandler(AbstractRequestHandler):
    """Handler for ChatGPTSlackHandler."""

    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("ChatGPTSlackHandler")(handler_input)

    def handle(self, handler_input):
        question = get_question(handler_input)
        # Remove the first word here as it likely matches a persons name
        # e.g. 'Slack me', 'Message Joe ...'
        # TODO: Check for matching name in future and use in Slack mentions if found in maintained lookup e.g. @Joe ...
        question_without_first_word = " ".join(question.split(" ")[1:])
        chatgpt_output = openai.Completion.create(
            model="text-davinci-003",
            prompt=question_without_first_word,
            max_tokens=1000,
            temperature=0
        ).choices[0].text
        res = send_slack_message(chatgpt_output)
        return handler_input.response_builder.speak(f"{res} sending to slack").ask("Anything else?").response


def send_slack_message(text):
    data = {
        "channel": channel,
        "text": text,
    }

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

    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return ask_utils.is_intent_name("AMAZON.HelpIntent")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        speak_output = "You can say hello to me! How can I help?"

        return (
            handler_input.response_builder
                .speak(speak_output)
                .ask(speak_output)
                .response
        )


class CancelOrStopIntentHandler(AbstractRequestHandler):
    """Single handler for Cancel and Stop Intent."""

    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return (ask_utils.is_intent_name("AMAZON.CancelIntent")(handler_input) or
                ask_utils.is_intent_name("AMAZON.StopIntent")(handler_input))

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        speak_output = "Goodbye!"

        return (
            handler_input.response_builder
                .speak(speak_output)
                .response
        )


class SessionEndedRequestHandler(AbstractRequestHandler):
    """Handler for Session End."""

    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return ask_utils.is_request_type("SessionEndedRequest")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response

        # Any cleanup logic goes here.

        return handler_input.response_builder.response


class IntentReflectorHandler(AbstractRequestHandler):
    """The intent reflector is used for interaction model testing and debugging.
    It will simply repeat the intent the user said. You can create custom handlers
    for your intents by defining them above, then also adding them to the request
    handler chain below.
    """

    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return ask_utils.is_request_type("IntentRequest")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        intent_name = ask_utils.get_intent_name(handler_input)
        speak_output = "You just triggered " + intent_name + "."

        return (
            handler_input.response_builder
                .speak(speak_output)
                # .ask("add a reprompt if you want to keep the session open for the user to respond")
                .response
        )


class CatchAllExceptionHandler(AbstractExceptionHandler):
    """Generic error handling to capture any syntax or routing errors. If you receive an error
    stating the request handler chain is not found, you have not implemented a handler for
    the intent being invoked or included it in the skill builder below.
    """

    def can_handle(self, handler_input, exception):
        # type: (HandlerInput, Exception) -> bool
        return True

    def handle(self, handler_input, exception):
        # type: (HandlerInput, Exception) -> Response
        logger.error(exception, exc_info=True)

        speak_output = "Sorry, I had trouble doing what you asked. Please try again."

        return (
            handler_input.response_builder
                .speak(speak_output)
                .ask(speak_output)
                .response
        )


# The SkillBuilder object acts as the entry point for your skill, routing all request and response
# payloads to the handlers above. Make sure any new handlers or interceptors you've
# defined are included below. The order matters - they're processed top to bottom.

sb = SkillBuilder()

sb.add_request_handler(LaunchRequestHandler())
sb.add_request_handler(ChatGPTIntentHandler())
sb.add_request_handler(ChatGPTSlackHandler())
sb.add_request_handler(HelpIntentHandler())
sb.add_request_handler(CancelOrStopIntentHandler())
sb.add_request_handler(SessionEndedRequestHandler())
sb.add_request_handler(
    IntentReflectorHandler())  # make sure IntentReflectorHandler is last so it doesn't override your custom intent
# handlers

sb.add_exception_handler(CatchAllExceptionHandler())

handler = sb.lambda_handler()
