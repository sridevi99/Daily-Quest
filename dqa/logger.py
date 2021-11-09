import os
import logging
import inspect
from google.oauth2 import service_account
import google.cloud.logging


class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(
                Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class GCPLogging(metaclass=Singleton):
    logger = None

    def __init__(self, parsed_json):

        credentials = service_account.Credentials.from_service_account_info(
            parsed_json)
        client = google.cloud.logging.Client(credentials=credentials)

        # Retrieves a Cloud Logging handler based on the environment
        # you're running in and integrates the handler with the
        # Python logging module. By default this captures all logs
        # at INFO level and higher
        client.setup_logging()
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(threadName)s - %(message)s",
            handlers=[
                logging.StreamHandler()
            ])

        self.logger = logging.getLogger(__name__ + '.logger')

    @staticmethod
    def __get_call_info():
        stack = inspect.stack()

        # stack[1] gives previous function ('info' in our case)
        # stack[2] gives before previous function and so on

        fn = stack[2][1]
        ln = stack[2][2]
        func = stack[2][3]

        return fn, func, ln

    def warn(self, message, *args):
        message = "{} - {} at line {}: {}".format(
            *self.__get_call_info(), message)
        self.logger.warning(message, *args)

    def error(self, message, *args):
        message = "{} - {} at line {}: {}".format(
            *self.__get_call_info(), message)
        self.logger.error(message, *args)

    def info(self, message, *args):
        message = "{} - {} at line {}: {}".format(
            *self.__get_call_info(), message)
        self.logger.info(message, *args)
