# Export total number of requests for all services in a site
# ArcGIS Server 10.3 or higher

import json

# For time-based functions
import time
import uuid
import datetime
import calendar

# For system tools
import sys
import os

# For reading passwords without echoing
import getpass

# For writing csv files
import csv

import configparser
import random

import requests
# urllib3 is included in requests but to manage the InsecureRequestWarning it was also imported directly
import urllib3
from urllib3.exceptions import InsecureRequestWarning
# Without disabled warnings, every request would print a red warning. This is because we have chosen
#   'verify=False' when making requests to secure services.
urllib3.disable_warnings(InsecureRequestWarning)


# Defines the entry point into the script
def main():

    # VARIABLES
    _ROOT_PROJECT_PATH = os.path.dirname(__file__)
    CREDENTIALS_PATH = os.path.join(_ROOT_PROJECT_PATH, "Docs/credentials.cfg")
    config = configparser.ConfigParser()
    config.read(filenames=CREDENTIALS_PATH)

    # CSV_OUTPUT_FILE_PATH = r"D:\inetpub\wwwroot\DOIT\StatusDashboard\temp\UsageStatistics.csv"  # PRODUCTION. *********DOIT folder DNE on imap01d
    CSV_OUTPUT_FILE_PATH = r"D:\scripts\StatusDashboard\UsageReport_MOD_testing\UsageStatistics.csv"    # TESTING

    PASSWORD = config["ags_server_credentials"]["password"]
    SERVER_MACHINE_NAMES = {0: config['ags_prod_machine_names']["machine1"],
                            1: config['ags_prod_machine_names']["machine2"],
                            2: config['ags_prod_machine_names']["machine3"],
                            3: config['ags_prod_machine_names']["machine4"]}
    SERVER_PORT_SECURE = config['ags_prod_machine_names']["secureport"]
    SERVER_ROOT_URL = "https://{machine_name}.mdgov.maryland.gov:{port}"
    USERNAME = config["ags_server_credentials"]["username"]

    # CLASSES
    class AdminObject:
        # TODO: Some of these are not common to all objects and should not be in Admin. Refactor
        ADMIN_SERVICES_ENDING = "arcgis/admin/services"
        GEODATA_ROOT = "https://geodata.md.gov/imap/rest/services"
        REST_URL_ENDING = "arcgis/rest/services"
        GENERATE_TOKEN_ENDING = "arcgis/admin/generateToken"
        USAGE_REPORT_ENDING__CREATE = "arcgis/admin/usagereports/add"  # 'add' is trigger for report creation
        USAGE_REPORT_ENDING__QUERY = "arcgis/admin/usagereports/{report_name}/data"  # 'data' is trigger for querying
        USAGE_REPORT_ENDING__DELETE = "arcgis/admin/usagereports/{report_name}/delete"  # 'delete' is trigger for deleting report

        def __init__(self, root_machine_url):
            self.admin_services_url = root_machine_url
            self.usage_reports_url__create = root_machine_url
            self.usage_reports_url__query = root_machine_url
            self.usage_reports_url__delete = root_machine_url
            self.rest_url_machine_root = root_machine_url

        @property
        def admin_services_url(self):
            return self.__admin_services_url

        @admin_services_url.setter
        def admin_services_url(self, value):
            self.__admin_services_url = f"{value}/{AdminObject.ADMIN_SERVICES_ENDING}"

        @property
        def usage_reports_url__create(self):
            return self.__usage_reports_url__create

        @usage_reports_url__create.setter
        def usage_reports_url__create(self, value):
            self.__usage_reports_url__create = f"{value}/{AdminObject.USAGE_REPORT_ENDING__CREATE}"

        @property
        def usage_reports_url__delete(self):
            return self.__usage_reports_url__delete

        @usage_reports_url__delete.setter
        def usage_reports_url__delete(self, value):
            self.__usage_reports_url__delete = f"{value}/{AdminObject.USAGE_REPORT_ENDING__DELETE}"

        @property
        def usage_reports_url__query(self):
            return self.__usage_reports_url__query

        @usage_reports_url__query.setter
        def usage_reports_url__query(self, value):
            self.__usage_reports_url__query = f"{value}/{AdminObject.USAGE_REPORT_ENDING__QUERY}"

        @property
        def rest_url_machine_root(self):
            return self.__rest_url_machine_root

        @rest_url_machine_root.setter
        def rest_url_machine_root(self, value):
            self.__rest_url_machine_root = f"{value}/{AdminObject.REST_URL_ENDING}"

    class FolderObject(AdminObject):
        """
        Example: 'https://gis-ags-imap02p.mdgov.maryland.gov:6443/arcgis/rest/services/Weather'
        FOLDER_URL_ENDING = "{folder}"
        """

        def __init__(self, name, root_machine_url):
            super().__init__(root_machine_url=root_machine_url)     # Needs to be instantiated before folder_url
            self.name = name
            self.folder_machine_url = name
            self.folder_geodata_url = name
            self.services_json = None
            self.service_objects_list = []

        @property
        def folder_geodata_url(self):
            return self.__folder_geodata_url

        @folder_geodata_url.setter
        def folder_geodata_url(self, value):
            self.__folder_geodata_url = f"{AdminObject.GEODATA_ROOT}/{value}"

        @property
        def folder_machine_url(self):
            return self.__folder_machine_url

        @folder_machine_url.setter
        def folder_machine_url(self, value):
            self.__folder_machine_url = f"{self.rest_url_machine_root}/{value}"

        def __str__(self):
            """
            Overriding the __str__ builtin to control the appearance of the object print-out for readability.
            :return: string
            """
            return f"FOLDER: {self.name}-->\n\turl on machine = {self.folder_machine_url}\n\turl on geodata = {self.folder_geodata_url}"

    class MachineObject:
        """Created to store machine properties and values."""

        def __init__(self, machine_name, root_url, token, folders):
            """
            Instantiate the machine objects
            :param machine_name: name of the server machine
            :param root_url: root url for machine
            :param token: the token generated by the machine for secure access
            :param folders: list of folders discovered during inspection of the services
            """
            self.machine_name = machine_name
            self.root_url = root_url
            self.token = token
            self.folder_names_list = folders

        def __str__(self):
            """
            Overriding the __str__ builtin to control the appearance of the object print-out for readability.
            :return: string
            """
            return f"MACHINE: {self.machine_name}-->\n\troot url = {self.root_url}\n\ttoken = {self.token}\n\tfolders list = {self.folder_names_list}"

    class NotJSONException(Exception):
        """Raised when the url for the request is malformed for our purposes and the server returns html, not json"""
        def __init__(self):
            pass

        def __str__(self):
            return "Content is not in JSON format. CJuice"

    class ReportObject(AdminObject):
        """"""
        def __init__(self, root_machine_url, master_urls_list, basic_request_json):
            super().__init__(root_machine_url)
            self.report_name_id = uuid.uuid4().hex
            self.now_time = datetime.datetime.utcnow()
            self.to_time = dt2ts(self.now_time) * 1000
            self.from_time = dt2ts(self.now_time - datetime.timedelta(hours=48)) * 1000 # TODO: Evaluate dt2ts. It is a function Jessie created.
            self.master_urls_list = master_urls_list
            self.json_definition = None
            self.report_json_params = basic_request_json
            # self.report_query_params = None
            self.report_url_create = None
            self.report_url_query = None
            self.report_url_delete = None

        @property
        def report_url_create(self):
            return self.__report_url_create

        @report_url_create.setter
        def report_url_create(self, value):
            create_url = self.usage_reports_url__create.format(report_name=self.report_name_id)
            # self.__report_url_delete = self.usage_reports_url__delete.format(report_name=self.report_name_id)
            self.__report_url_create = create_url

        @property
        def report_url_delete(self):
            return self.__report_url_delete

        @report_url_delete.setter
        def report_url_delete(self, value):
            delete_url = self.usage_reports_url__delete.format(report_name=self.report_name_id)
            # self.__report_url_delete = self.usage_reports_url__delete.format(report_name=self.report_name_id)
            self.__report_url_delete = delete_url

        @property
        def report_url_query(self):
            return self.__report_url_query

        @report_url_query.setter
        def report_url_query(self, value):
            query_url = self.usage_reports_url__query.format(report_name=self.report_name_id)
            # self.__report_url_query = self.usage_reports_url__query.format(report_name=self.report_name_id)
            self.__report_url_query = query_url

        @property
        def json_definition(self):
            return self.__json_definition

        @json_definition.setter
        def json_definition(self, value):
            # Create report JSON definition. This json object goes into the json object submitted to the server.
            #   The object details indicate what is to be put into the report when it is built
            #   'resourceURIs' is a list of all service and folder urls per Jessie design
            #   NOTE: When python provides you with a dictionary it does so with single quotes not double quotes as
            #       I have indicated below. Single quotes are not recognized as valid json so json.dumps() must be used
            #       to create a json string with double quotes.
            # TODO: NOTE: I switched the True to "True" 20180829 to see if it was causing the JSON object issue
            self.__json_definition = {"reportname": self.report_name_id,
                                      "since": "CUSTOM",
                                      "from": int(self.from_time),
                                      "to": int(self.to_time),
                                      "queries": [
                                          {"resourceURIs": self.master_urls_list,
                                           "metrics": ["RequestCount"]}
                                      ],
                                      "aggregationInterval": 60,
                                      "metadata": {"temp": "True",
                                                   "tempTimer": 1454109613248}
                                      }

        @property
        def report_json_params(self):
            return self.__report_json_params

        @report_json_params.setter
        def report_json_params(self, value):
            value.update({"usagereport": self.json_definition})
            # print(f"Report Json Params: {value}")   # TESTING
            self.__report_json_params = value

    class ServiceObject(AdminObject):
        """
        Example: 'https://gis-ags-imap02p.mdgov.maryland.gov:6443/arcgis/rest/services/Weather/MD_StormSurge/MapServer'
        REST_URL_END = "{folder}/{service_name}/{type}
        """

        # SERVICE_ADMIN_PROPERTIES_URL_ENDING = "{service_name}.{service_type}"

        def __init__(self, folder, service_json, root_machine_url):
            super().__init__(root_machine_url=root_machine_url)
            self.folder = folder
            self.service_name = service_json
            self.service_type = service_json
            self.service_url = None
            self.service_admin_properties_url = None

        @property
        def service_name(self):
            return self.__service_name

        @service_name.setter
        def service_name(self, value):
            try:
                self.__service_name = value['name']
            except KeyError as ke:
                print(f"KeyError: 'name' not found in services json for this service. {ke}")

        @property
        def service_type(self):
            return self.__service_type

        @service_type.setter
        def service_type(self, value):
            try:
                self.__service_type = value['type']
            except KeyError as ke:
                print(f"KeyError: 'type' not found in services json for this service. {ke}")

        @property
        def service_admin_properties_url(self):
            return self.__service_admin_properties_url

        @service_admin_properties_url.setter
        def service_admin_properties_url(self, value):
            self.__service_admin_properties_url = f"{self.admin_services_url}/{self.service_name}.{self.service_type}"

        @property
        def service_url(self):
            return service.__service_admin_properties_url

        @service_url.setter
        def service_url(self, value):
            self.__service_admin_properties_url = f"{self.rest_url_machine_root}/{self.service_name}/{self.service_type}"

        def __str__(self):
            """
            Overriding the __str__ builtin to control the appearance of the object print-out for readability.
            :return: string
            """
            return f"SERVICE: {self.service_name}-->\n\ttype = {self.service_type}\n\tfolder = {self.folder}"

    # FUNCTIONS
    def create_params_for_request(token_action=None, json_payload=None, format="json"):
        """
        TODO
        Create parameters to be submitted with the request.
        :param token_action: route to be taken when creating the parameters
        :return: dictionary of parameters
        """
        if token_action == None and json_payload == None:
            values = {'f': format}
        elif token_action == "getToken":
            values = {'username': USERNAME, 'password': PASSWORD, 'client': 'requestip', 'f': format}
        elif token_action != None and json_payload != None:
            values = {'token': token_action, 'f': format}
            values.update(json_payload)
        else:
            values = {'token': token_action, 'f': format}
        return values

    def clean_url_slashes(url):
        """
        Standardize the slashes when use of os.path.join() with forward slashes in url's.
        os.path.join() uses back slashes '\' while http uses forward slashes '/'
        :param url: url to be examined
        :return: standardized url string
        """
        url = url.replace("\\", "/")
        return url

    def create_master_url_list(objects_list):
        # need a list of folder url's
        # folder_urls = [obj.folder_machine_url for obj in objects_list]
        master_list = []
        for obj_fold in objects_list:
            master_list.append(obj_fold.folder_machine_url)
            for obj_serv in obj_fold.service_objects_list:
                master_list.append(obj_serv.service_admin_properties_url)
        return master_list

    def create_random_int(upper_integer):
        """
        Create and return a random integer from 0 to one less than the upper range value.
        :param upper_integer: upper integer of range to be used
        :return: integer
        """
        options = upper_integer - 1
        spot = random.randint(0, options)
        return spot

    def get_response(url, params):
        """
        TODO
        Submit a request with parameters to a url and inspect the response json for the specified key of interest.
        :param url: url to which to make a request
        :param params: parameters to accompany the request
        :return: content of json if key present in response
        """
        # To deal with mixed path characters between url syntax and os.path.join use of "\"
        url = clean_url_slashes(url)

        try:
            # Jessie discovered "verify" option and set to False to bypass the ssl issue
            response = requests.post(url=url, data=params, verify=False)
        except Exception as e:
            print("Error in response from requests: {}".format(e))
            exit()
        else:
            print(f"RESPONSE URL: {response.url}")
            try:
                if "html" in response.headers["Content-Type"]:
                    raise NotJSONException
                response_json = response.json()
            except json.decoder.JSONDecodeError as jde:
                print("Error decoding response to json: {}".format(jde))
                print(response)
                exit()
            except NotJSONException as NJE:
                print(f"Response appears to be html, not json.")
                print(response.url)
                print(response.headers)
                # print(response.text)
                exit()
            return response_json

    def search_json_for_key(response_json, search_key):
        try:
            value = response_json[search_key]
        except KeyError as ke:
            print("KeyError: {}".format(ke))
            exit()
        except TypeError as te:
            print("TypeError: {}".format(te))
            print(response_json)
            exit()
        else:
            return value

    def write_response_to_csv(response, csv_path):
        # Read the response as a csv
        csvreader = csv.reader(response)
        # Open csv file
        with open(csv_path, 'wb') as csv_file_handler:
            csvwriter = csv.writer(csv_file_handler, dialect='excel')
            csvwriter.writerows(csvreader)
            # csv_file_handler.close()
            # response.close()
        return

    def dt2ts(dt):
        return calendar.timegm(dt.utctimetuple())

    # FUNCTIONALITY
    #   Need a machine to which to make a request. Select at random from 4 total since we are bypassing web adaptor.
    machine = SERVER_MACHINE_NAMES[create_random_int(upper_integer=len(SERVER_MACHINE_NAMES))]

    #   Need a token to make secure requests
    root_server_url = SERVER_ROOT_URL.format(machine_name=machine, port=SERVER_PORT_SECURE)
    generate_token_url = os.path.join(root_server_url, AdminObject.GENERATE_TOKEN_ENDING)
    token_params = create_params_for_request(token_action="getToken")
    token_response = get_response(url=generate_token_url, params=token_params)
    token = search_json_for_key(response_json=token_response, search_key="token")
    print(f"Token: {token}")

    #   Need to make a secure request for response as JSON to be able to access folders and services details
    request_params_result = create_params_for_request(token_action=token)   # TODO: This basic kind of param creation occurs many times in code. Refactor ?
    admin_services_full_url = clean_url_slashes(os.path.join(root_server_url, AdminObject.ADMIN_SERVICES_ENDING))   # TODO: Refactorable. Added to AdminObject
    folders_request_response = get_response(url=admin_services_full_url, params=request_params_result)

    #   Need folder names list and to clean list; Remove System & Utilities, & append entry for root folder, per Jessie
    #   Note: Noticed that Jessie also included 'GeoprocessingServices', but did not in statusdashboard script
    folder_names_raw = search_json_for_key(response_json=folders_request_response, search_key="folders")
    remove_folders = ["System", "Utilities", "GeoprocessingServices"]
    folder_names_clean = list(set(folder_names_raw) - set(remove_folders))
    folder_names_clean.append("")
    folder_names_clean.sort()

    #   Create a machine object for the selected ArcGIS Server machine. To store related values in object.
    machine_object = MachineObject(machine_name=machine,
                                   root_url=root_server_url,
                                   token=token,
                                   folders=folder_names_clean)
    print(f"MACHINE: {machine_object}")

    #   Need a single list containing all folder url's AND all service url's from within all of those folders.
    #   It is passed to the server and indicates the resourceURIs for which metrics will be built in the query process
    #   Use Folder objects to store folder urls and service objects containing urls
    list_of_folder_objects = [FolderObject(name=folder_name, root_machine_url=machine_object.root_url) for folder_name
                              in machine_object.folder_names_list]

    #   For each folder, need a list of service objects for services in that folder
    for fold_obj in list_of_folder_objects:

        # Need a url to which to make a request to learn the services within
        service_request_params = create_params_for_request(token_action=token)
        services_request_response = get_response(url=fold_obj.folder_machine_url, params=service_request_params)
        services_json = search_json_for_key(response_json=services_request_response, search_key="services")

        # Need to store the inventory of services that are within each folder
        for service in services_json:
            serv_obj = ServiceObject(folder=fold_obj.name,
                                     service_json=service,
                                     root_machine_url=machine_object.root_url)
            fold_obj.service_objects_list.append(serv_obj)

    master_url_list = create_master_url_list(list_of_folder_objects)

    # Need to create a new report object for use in generating report on server.
    basic_secure_params = create_params_for_request(token_action=machine_object.token)
    report_object = ReportObject(root_machine_url=machine_object.root_url,
                                 master_urls_list=master_url_list,
                                 basic_request_json=basic_secure_params)

    # Report is created on the server. No response is needed. The variable isn't used afterward for that reason.
    # FIXME: Is the report created by my process? NO
    #   TODO: If I manually paste the printed json into the web interface it works, status is success, and I can see it when I go to the machine.
    #   TODO: But, I can't hit the report by the url generated in my process for querying the report because my process never successfully creates it
    # ERROR RESPONSE: {'status': 'error', 'messages': ['Use JSON in parameter usagereport.'], 'code': 500}
    # IDEA: Could be use of single over double quotes,  ANSWER: Didn't make a difference in script
    # When I attempt to hit 'add' using url with query string including token and format I get the following...
    #   ERROR RESPONSE: {"status":"error","messages":["Only HTTP POST method is supported on this operation."]}
    #   In the code I am using the requests.post so shouldn't be an issue with 'get' vs 'post'
    # ERROR RESPONSE: {'status': 'error', 'messages': ["A JSONObject text must begin with '{' at character 1 of token"], 'code': 500}
    #   Changed the True to "True" in the usage report json object

    # print(f"Create URL: {report_object.report_url_create}")
    # print(f"JSON: \n{report_object.report_json_params}")
    # json_params_as_string_with_double_quotes = json.dumps(report_object.report_json_params)

    usage_report_params = create_params_for_request(token_action=machine_object.token,
                                                    json_payload=report_object.report_json_params)
    print(usage_report_params)
    x = get_response(url=report_object.report_url_create, params=usage_report_params)
    print(x)
    # print(x['status'])


    # _____________________________________________
    # Create the json object to be posted to the server for creating the report
    # postdata = {'usagereport': json.dumps(statsDefinition)}

    # Report is created on the server. No response is needed. The variable isn't used afterward for that reason.
    # createReportResult = postAndLoadJSON(statsCreateReportURL, token, postdata)

    # Query the newly created report. The 'data' word must cause the contents to be accessed and returned
    # statsQueryReportURL = "https://{serverName}/imap/admin/usagereports/{reportName}/data".format(serverName=serverName,
    #                                                                                               reportName=reportName)
    # _____________________________________________


    # Need to get the report contents using the query url
    # TODO: This is from Jessie. Not certain of its function and if it will work with the machine name model
    # IDEA: run through using the machine name and then paste that json into browser to see if machine name works
    # post_data_query = {'filter': {'machines': '*'}}
    post_data_query = {'filter': {'machines': [machine_object.machine_name]}}
    report_query_params = create_params_for_request(token_action=machine_object.token,
                                                    json_payload=post_data_query,
                                                    format='csv')
    print(report_object.report_url_query)
    print(report_query_params)

    exit()  #                                                                                                         WORKING UP TO HERE


    report_query_response = get_response(url=report_object.report_url_query, params=report_query_params)

    # Need to write the report content to csv file
    write_response_to_csv(response=report_query_response, csv_path=CSV_OUTPUT_FILE_PATH)

    # Need to delete the report from the server to reduce bloat
    report_delete_params = create_params_for_request(token_action=machine_object.token)
    get_response(url=report_object.report_url_delete, params=report_delete_params)


    # TODO: Why is this needed?
    # _____________________________________________
    # post_data_query = {'filter': {'machines': '*'}}

    # Make call to query report url, get the report content, and write the report to a csv file at the indicated path
    # postAndLoadCSV(statsQueryReportURL, CSV_OUTPUT_FILE_PATH, token, post_data_query)

    # Cleanup (delete) statistics report so that it can be recreated the next time.
    #   Build the url and make the call to the url for deleting.
    # print("Before delete")
    # statsDeleteReportURL = "https://{serverName}/imap/admin/usagereports/{reportName}/delete".format(serverName=serverName,
    #                                                                                                  reportName=reportName)
    # deleteReportResult = postAndLoadJSON(statsDeleteReportURL, token)
    # _____________________________________________


    print("Export complete!")
    return








# A function that makes an HTTP POST request and returns the result JSON object
# def postAndLoadCSV(url, fileName, token = None, postdata = None):
#     """
#     Appears to create a json object containing a token and format = csv, hits the url (the query report url per its
#     only implementation), open the output file, write the report content to the file, and close out.
#     """
#     if not postdata:    # None evaluates to False
#         postdata = {}
#
#     # Add token to POST data if not already present and supplied
#     if token and 'token' not in postdata:
#         postdata['token'] = token
#
#     # Add format specifier to POST data if not already present. This is where the format is set to csv.
#     if 'f' not in postdata:
#         postdata['f'] = 'csv'
#
#     # Encode data and POST to server
#     postdata = urllib.urlencode(postdata)
#     response = urllib2.urlopen(url, data=postdata)
#
#     print('post data')
#     if (response.getcode() != 200):
#         response.close()
#         raise Exception('Error performing request to {0}'.format(url))
#
#     # # Read the response as a csv
#     # csvreader = csv.reader(response)
#     #
#     # # Open output file
#     # output = open(fileName, 'wb')
#     # csvwriter = csv.writer(output, dialect='excel')
#     # csvwriter.writerows(csvreader)
#     # output.close()
#     # response.close()
#     #
#     # return


# A function that makes an HTTP POST request and returns the result JSON object
# def postAndLoadJSON(url, token=None, postdata=None):
#     """
#     Appears to make a request to server url, includes token and format as json, and returns response as json object.
#     """
#     if not postdata:
#         postdata = {}
#
#     # Add token to POST data if not already present and supplied
#     if token and 'token' not in postdata:
#         postdata['token'] = token
#
#     # Add JSON format specifier to POST data if not already present
#     if 'f' not in postdata:
#         postdata['f'] = 'json'
#
#     # Encode data and POST to server
#     postdata = urllib.urlencode(postdata)
#     response = urllib2.urlopen(url, data=postdata)
#     print('post data')
#
#     if response.getcode() != 200:
#         response.close()
#         raise Exception('Error performing request to {0}'.format(url))
#
#     data = response.read()
#     response.close()
#     print('postandloadjson')
#
#     # Check that data returned is not an error object
#     if not assertJsonSuccess(data):
#         raise Exception("Error returned by operation. " + data)
#
#     # Deserialize response into Python object
#     return json.loads(data)


# A function that enumerates all services in all folders on site
# def getServiceList(serverName, serverPort, token):
#     """
#     Appears to hit the root system folder, get a list of all folder names, hit each folder url, get a list of service
#     objects, and build a list of folder url's AND all service
#     url's.
#     TODO: Unclear why the folder url and the service urls are all in one list ?
#     :return: list of folder urls AND all service urls
#     """
#     rooturl = "https://" + serverName + "/imap/admin/services".format(serverName, serverPort)
#
#     # Making call to admin services url, including a token and format = json, getting back root content as json
#     root = postAndLoadJSON(rooturl, token)
#
#     # Services list will hold folder url's and exact url's to all services
#     services = []
#
#     # Accessing the folders using the 'folders' key in the root json. Is a list of folder names.
#     folders = root['folders']
#
#     # Iterating through folders
#     for folderName in folders:
#
#         # Exclude certain folders
#         if folderName != "System" and folderName != "Utilities" and folderName != "GeoprocessingServices":
#
#             # Append url for each folder of services to a list
#             services.append("services/" + folderName)
#
#             # Builds a folder url based on the imap/admin/services root
#             folderurl = "{rooturl}/{folderName}".format(rooturl=rooturl, folderName=folderName)
#
#             # Make a request to server for contents of folder and get response as json object
#             folder = postAndLoadJSON(folderurl, token)
#
#             # For each service object in the folder, append the full url for the service specific to its service type
#             for service in folder['services']:
#                 # eg URL - https://geodata.md.gov/imap/admin/services/Agriculture/MD_AgriculturalDesignations.MapServer
#                 services.append("services/{folderName}/{serviceName}.{serviceType}".format(folderName=folderName,
#                                                                                            serviceName=service['serviceName'],
#                                                                                            serviceType=service['type']))
#
#     return services
    
#A function to generate a token given username, password and the adminURL.
# def getToken(username, password, serverName, serverPort):
#     # Token URL is typically https://server[:port]/arcgis/admin/generateToken
#     tokenURL = "/imap/admin/generateToken"
#
#     # URL-encode the token parameters
#     params = urllib.urlencode({'username': username, 'password': password, 'client': 'requestip', 'f': 'json'})
#
#     headers = {"Content-type": "application/x-www-form-urlencoded", "Accept": "text/plain"}
#
#     # Connect to URL and post parameters
#     httpsConn = httplib.HTTPSConnection(serverName, serverPort)
#     httpsConn.request("POST", tokenURL, params, headers)
#
#     # Read response
#     response = httpsConn.getresponse()
#     print(response.read())
#     if (response.status != 200):
#         httpsConn.close()
#         print("Error while fetching tokens from the admin URL. Please check the URL and try again.")
#         return
#     else:
#         data = response.read()
#         httpsConn.close()
#
#         # Check that data returned is not an error object
#         if not assertJsonSuccess(data):
#             return
#
#         # Extract the token from it
#         token = json.loads(data)
#         return token['token']
#
# #A function that checks that the input JSON object
#  is not an error object.    
# def assertJsonSuccess(data):
#     obj = json.loads(data)
#     if 'status' in obj and obj['status'] == "error":
#         print("Error: JSON object returns an error. " + str(obj))
#         return False
#     else:
#         return True
    
        
# Script start
if __name__ == "__main__":
    main()
