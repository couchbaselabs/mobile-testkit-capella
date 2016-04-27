import logging
import os
import shutil
from zipfile import ZipFile
import time
import re

from requests.sessions import Session
from requests.exceptions import ConnectionError
from requests.adapters import HTTPAdapter

from constants import *
import requests

def version_and_build(full_version):
    version_parts = full_version.split("-")
    assert (len(version_parts) == 2)
    return version_parts[0], version_parts[1]

class LiteServ:

    def __init__(self, platform, version_build, hostname, port):

        supported_platforms = ["macosx", "android", "net"]
        if platform not in supported_platforms:
            raise ValueError("Unsupported version of LiteServ")

        self._platform = platform
        self._version_build = version_build

        if self._platform == "macosx":
            self.extracted_file_name = "couchbase-lite-macosx-{}".format(self._version_build)
        elif self._platform == "android":
            # TODO
            pass
        elif self._platform == "net":
            # TODO
            pass

        self._url = "http://{}:{}".format(hostname, port)
        logging.info("Launching Listener on {}".format(self._url))

        # self._retry_session = Session()
        # self._retry_session.mount('https://', HTTPAdapter(max_retries=MAX_RETRIES))

        self._session = Session()

    def download_liteserv(self):

        logging.info("Downloading {} LiteServ, version: {}".format(self._platform, self._version_build))
        if self._platform == "macosx":
            version, build = version_and_build(self._version_build)
            file_name = "couchbase-lite-macosx-enterprise_{}.zip".format(self._version_build)
            if version == "1.2.0":
                url = "{}/couchbase-lite-ios/release/{}/macosx/{}/{}".format(LATEST_BUILDS, version, self._version_build, file_name)
            else:
                url = "{}/couchbase-lite-ios/{}/macosx/{}/{}".format(LATEST_BUILDS, version, self._version_build, file_name)
        elif self._platform == "android":
            # TODO
            pass
        elif self._platform == "net":
            # TODO
            pass

        # Change to package dir
        os.chdir(BINARY_DIR)

        # Download the packages
        print("Downloading: {}".format(url))
        resp = requests.get(url)
        resp.raise_for_status()
        with open(file_name, "wb") as f:
            f.write(resp.content)

        # Unzip the package
        with ZipFile(file_name) as zip_f:
            zip_f.extractall(self.extracted_file_name)

        # Make binary executable
        os.chmod("{}/LiteServ".format(self.extracted_file_name), 0755)

        # Remove .zip file
        os.remove(file_name)

        # Change back to root dir
        os.chdir("../..")

    def get_liteserv_binary_path(self):

        if self._platform == "macosx":
            binary_path = "{}/{}/LiteServ".format(BINARY_DIR, self.extracted_file_name)
        elif self._platform == "android":
            # TODO
            pass
        elif self._platform == "net":
            # TODO
            pass

        return binary_path

    def remove_liteserv(self):
        logging.info("Removing {} LiteServ, version: {}".format(self._platform, self._version_build))
        os.chdir(BINARY_DIR)
        shutil.rmtree(self.extracted_file_name)
        os.chdir("../..")

    def verify_liteserv_launched(self):
        count = 0
        wait_time = 1
        while count < MAX_RETRIES:
            try:
                resp = self._session.get(self._url)
                # If request does not throw, exit retry loop
                break
            except ConnectionError as ce:
                logging.info("LiteServ may not be launched (Retrying): {}".format(ce))
                time.sleep(wait_time)
                count += 1
                wait_time *= 2

        if count == MAX_RETRIES:
            raise RuntimeError("Could not connect to LiteServ")

        resp_json = resp.json()
        lite_version = resp_json["vendor"]["version"]

        # Validate that the version launched is the expected LiteServ version
        # LiteServ: 1.2.1 (build 13)
        version, build = version_and_build(self._version_build)
        expected_version = "{} (build {})".format(version, build)
        if lite_version != expected_version:
            raise ValueError("Expected version does not match actual version: Expected={}  Actual={}".format(expected_version, lite_version))

        logging.info ("LiteServ: {} is running".format(lite_version))

        return self._url
