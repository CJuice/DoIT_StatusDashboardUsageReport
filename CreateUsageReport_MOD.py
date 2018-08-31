"""
Creates, queries, and deletes a usage report on the total number of requests for all services in a site,
by machine specific calls rather than using the web adaptor.

This script is uniquely designed to access the ArcGIS Server servers (machines) in our iMAP 3.0 environment by their
machine name rather than going through the Web Adaptor. When we moved to ESRI's 10.6 environment the previous script
failed and we encountered errors related to tokens and client mismatching. A valid, working token, would be rejected
randomly and frequently. We first adapted using a while loop for handling failures. The loop caused repeated calls
until a call when through and this is how we bypassed the issue. The issue appeared on multiple scripts so an overhaul
was performed and we abandoned calls to the web adaptor and instead hit the machiens by their direct path referencing
their name rather than using the domain.
Contains AdminObject, FolderObject, MachineObject, ReportObject, ServiceObject, and NotJSONException classes.
Original Design: JCahoon
Overhaul Author: CJuice
Date: 20180831
Revised: This script is an overhaul of a previous script. The previous script used Python 2.7 and this script was
 designed with 3.7. The functionality and steps of the previous script were recreated herein but the code now uses
 the requests module and is consequently significantly different. This script was designed at ArcGIS Server 10.6
Revised:
"""


def main():
    """
    Run the script if it is the primary call and not an import to another script.
    :return: None
    """

    # IMPORTS
    import calendar
    import configparser
    import datetime
    import json
    import os
    import random
    import requests
    import uuid
    # NOTE: Believe urllib3 is included in requests module but to manage InsecureRequestWarning was also imported.
    #   Without disabled warnings, every request would print a red warning. This is because we have chosen
    #   'verify=False' when making requests to secure services.
    import urllib3
    from urllib3.exceptions import InsecureRequestWarning
    urllib3.disable_warnings(InsecureRequestWarning)

    # VARIABLES
    _ROOT_PROJECT_PATH = os.path.dirname(__file__)
    CREDENTIALS_PATH = os.path.join(_ROOT_PROJECT_PATH, "Docs/credentials.cfg")
    config = configparser.ConfigParser()
    config.read(filenames=CREDENTIALS_PATH)

    # CSV_OUTPUT_FILE_PATH = r"D:\inetpub\wwwroot\DOIT\StatusDashboard\temp\UsageStatistics.csv"               # PRODUCTION.
    # *********DOIT folder DNE on imap01d
    CSV_OUTPUT_FILE_PATH = r"D:\scripts\StatusDashboard\UsageReport_MOD_testing\UsageStatistics.csv"           # TESTING
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
        """
        The AdminObject class represents the needed functionality of ArcGIS Server admin access. Not all functionality
        is represented, only that which is relevant to the needed processes. There are portions of url's that are
        constants. These are made available to child classes that inherit AdminObject.
        """

        ADMIN_SERVICES_ENDING = "arcgis/admin/services"
        GENERATE_TOKEN_ENDING = "arcgis/admin/generateToken"
        GEODATA_ROOT = "https://geodata.md.gov/imap/rest/services"
        REST_URL_ENDING = "arcgis/rest/services"

        def __init__(self, root_machine_url):
            """
            Instantiate the AdminObject, setting the admin_services_url and the rest_url_machine_root attributes
            using the setter/getter mutator methods.

            :param root_machine_url: url specific to the machine being accessed in the requests. In bypassing the web
            adaptor and making machine specific calls this became necessary
            """
            self.admin_services_url = root_machine_url
            self.rest_url_machine_root = root_machine_url

        @property
        def admin_services_url(self):
            return self.__admin_services_url

        @admin_services_url.setter
        def admin_services_url(self, value):
            self.__admin_services_url = f"{value}/{AdminObject.ADMIN_SERVICES_ENDING}"

        @property
        def rest_url_machine_root(self):
            return self.__rest_url_machine_root

        @rest_url_machine_root.setter
        def rest_url_machine_root(self, value):
            self.__rest_url_machine_root = f"{value}/{AdminObject.REST_URL_ENDING}"

    class FolderObject(AdminObject):
        """
        The FolderObject class represents a service folder in the server services and inherits from AdminObject.

        This class overrides the __str__ builtin from AdminObject to provide meaningful printing of the object.
        Machine Name Path Example: 'https://gis-ags-imap02p.mdgov.maryland.gov:6443/arcgis/rest/services/Weather'
        """

        def __init__(self, name, root_machine_url):
            """
            Instantiate the FolderObject, first instantiating the inherited AdminObject using super(), and set
            attributes using the setter/getter mutator methods. Name is the name of the folder, folder_machine_url is
            the url to the folder using the machine path, folder_geodata_url is the url to the folder using the
            geodata.md.gov path, folder_short_services_url is the short/relative path for making calls for services when
            building usage report (doesn't reference the machine or geodata root portion of the url), and
            service_objects_list is a list intended for storing all ServiceObject objects for services within a folder.
            :param name: Name of the services folder
            :param root_machine_url: url for the machine, rather than the web adaptor path
            """
            super().__init__(root_machine_url=root_machine_url)     # Needs to be instantiated before folder_url
            self.name = name
            self.folder_geodata_url = name
            self.folder_machine_url = name
            self.folder_short_services_url = name
            # self.services_json = None   # TODO: Used?
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

        @property
        def folder_short_services_url(self):
            return self.__folder_short_service_url

        @folder_short_services_url.setter
        def folder_short_services_url(self, value):
            self.__folder_short_service_url = f"services/{value}"

        def __str__(self):
            """
            Override the __str__ builtin to control the appearance of the object print-out for readability.
            :return: string
            """
            return f"FOLDER: {self.name}-->\n\turl on machine = {self.folder_machine_url}\n\t" \
                   f"url on geodata = {self.folder_geodata_url}"

    class MachineObject:
        """
        The MachineObject class represents a server machine and stores properties and values.

        This class overrides the __str__ builtin to provide meaningful printing of the object.
        """

        def __init__(self, machine_name, root_url, security_token, folder_names=None):
            """
            Instantiate the machine object, setting the machine name, the root machine url, the token for accessing
            secure services, and the list for storing folder names.
            Machine name is name of the server machine and is necessary because the web adaptor is being bypassed
            and the servers are being hit directly using their machine name. The root url for the machine uses the
            machine name. The token is the key created by the server for accessing secure services. The folder names
            is a list of service folder names on the machine.
            :param machine_name: name of the server machine
            :param root_url: root url for machine
            :param security_token: the token generated by the machine for secure access
            :param folder_names: list of folders discovered during inspection of the services
            """
            self.machine_name = machine_name
            self.root_url = root_url
            self.token = security_token
            self.folder_names_list = folder_names

        def __str__(self):
            """
            Overriding the __str__ builtin to control the appearance of the object print-out for readability.
            :return: string
            """
            return f"MACHINE: {self.machine_name}-->\n\troot url = {self.root_url}\n\ttoken = {self.token}\n\t" \
                   f"folders list = {self.folder_names_list}"

    class NotJSONException(Exception):
        """
        Raise when the url for the request is malformed for our purposes and the server returns html, not json.

        Inherits from Exception class.
        """

        def __init__(self):
            """Instantiate the object and pass"""
            pass

        def __str__(self):
            """Override the builtin __str__ method"""
            return "Content is not in JSON format. CJuice"

    class ReportObject(AdminObject):
        """
        The ReportObject class is for service usage reports from ArcGIS Servers. Not all functionality
        is represented, only that which is relevant to the needed processes. There are portions of url's that are
        constants.
        Notes: 'add' is trigger for report creation, 'data' is trigger for querying, 'delete' is trigger for
        deleting report
        """

        USAGE_REPORT_ENDING__CREATE = "arcgis/admin/usagereports/add"
        USAGE_REPORT_ENDING__QUERY = "arcgis/admin/usagereports/{report_name}/data"
        USAGE_REPORT_ENDING__DELETE = "arcgis/admin/usagereports/{report_name}/delete"

        def __init__(self, root_machine_url, master_urls_list, basic_request_json):
            """
            Instantiate the ReportObject, first instantiating the inherited AdminObject using super(), and set
            attributes using the setter/getter mutator methods. Setting order preserves/honors dependencies. Sets a
            unique name for the report, the current time, the time span of the report query using the to and from
            attributes, the usage report urls for creating querying and deleting a report, the json definition for
            specific report content, and the packaged json object for passing to the server for usagereport generation.

            :param root_machine_url: root url for machine
            :param master_urls_list: list of master folder and service urls
            :param basic_request_json: json including token and format
            """
            super().__init__(root_machine_url)
            self.report_name_id = uuid.uuid4().hex
            self.now_time = datetime.datetime.utcnow()
            self.to_time = ReportObject.datetime_to_timestamp_seconds(self.now_time) * 1000
            self.from_time = ReportObject.datetime_to_timestamp_seconds(self.now_time - datetime.timedelta(hours=48)) * 1000
            self.usage_reports_url__create = root_machine_url
            self.usage_reports_url__delete = root_machine_url
            self.usage_reports_url__query = root_machine_url
            self.report_url_create = None
            self.report_url_delete = None
            self.report_url_query = None
            self.master_urls_list = master_urls_list
            self.json_definition = None
            self.report_json_params = basic_request_json

        @staticmethod
        def datetime_to_timestamp_seconds(date_time_object):
            """
            Take a date time object and returns the corresponding Unix timestamp value, assuming an epoch of 1970

            :param date_time_object: datetime object
            :return: seconds as integer
            """
            return calendar.timegm(date_time_object.utctimetuple())

        @property
        def usage_reports_url__create(self):
            return self.__usage_reports_url__create

        @usage_reports_url__create.setter
        def usage_reports_url__create(self, value):
            self.__usage_reports_url__create = f"{value}/{ReportObject.USAGE_REPORT_ENDING__CREATE}"

        @property
        def usage_reports_url__delete(self):
            return self.__usage_reports_url__delete

        @usage_reports_url__delete.setter
        def usage_reports_url__delete(self, value):
            self.__usage_reports_url__delete = f"{value}/{ReportObject.USAGE_REPORT_ENDING__DELETE}"

        @property
        def usage_reports_url__query(self):
            return self.__usage_reports_url__query

        @usage_reports_url__query.setter
        def usage_reports_url__query(self, value):
            self.__usage_reports_url__query = f"{value}/{ReportObject.USAGE_REPORT_ENDING__QUERY}"

        @property
        def report_url_create(self):
            return self.__report_url_create

        @report_url_create.setter
        def report_url_create(self, value):
            create_url = self.usage_reports_url__create.format(report_name=self.report_name_id)
            self.__report_url_create = create_url

        @property
        def report_url_delete(self):
            return self.__report_url_delete

        @report_url_delete.setter
        def report_url_delete(self, value):
            delete_url = self.usage_reports_url__delete.format(report_name=self.report_name_id)
            self.__report_url_delete = delete_url

        @property
        def report_url_query(self):
            return self.__report_url_query

        @report_url_query.setter
        def report_url_query(self, value):
            query_url = self.usage_reports_url__query.format(report_name=self.report_name_id)
            self.__report_url_query = query_url

        @property
        def json_definition(self):
            return self.__json_definition

        @json_definition.setter
        def json_definition(self, value):
            """
            Create usage report JSON definition. This json object goes into the json object submitted to the server. The
            object details indicate what is to be put into the report when it is built. 'resourceURIs' is a list of
            all service and folder urls per Jessie design and she may have borrowed the code from ESRI demo

            :param value:
            :return:
            """

            self.__json_definition = {"reportname": self.report_name_id,
                                      "since": "CUSTOM",
                                      "from": int(self.from_time),
                                      "to": int(self.to_time),
                                      "queries": [
                                          {"resourceURIs": self.master_urls_list,
                                           "metrics": ["RequestCount"]}
                                      ],
                                      "aggregationInterval": 60,
                                      "metadata": {"temp": True,
                                                   "tempTimer": 1454109613248}
                                      }

        @property
        def report_json_params(self):
            return self.__report_json_params

        @report_json_params.setter
        def report_json_params(self, value):
            """
            NOTE: Proved absolutely essential for the usagereport value to be processed by json.dumps(). Received an
            error in response saying 'A JSONObject text must begin with '{' at character 1 of ...'
            :param value: json including the token and format
            :return:
            """
            value.update({"usagereport": json.dumps(self.json_definition)})
            self.__report_json_params = value

    class ServiceObject(AdminObject):
        """
        The ServiceObject class is for storing values related to an ArcGIS server service in a services folder and
        inherits from AdminObject.

        This class overrides the __str__ builtin to provide meaningful printing of the object.
        """

        def __init__(self, folder, service_json, root_machine_url):
            """
            Instantiate the ServiceObject class, first instantiating the inherited AdminObject using super(), and set
            attributes using the setter/getter mutator methods. Service name is the name of
            the service and the type is limited to ESRI types (eg. FeatureService)
            :param folder: name of the service folder
            :param service_json: json content of services key in response json
            :param root_machine_url: url for the machine, rather than the web adaptor path
            """
            super().__init__(root_machine_url=root_machine_url)
            self.folder = folder
            self.service_name = service_json
            self.service_type = service_json
            self.service_short_services_url = None

        @property
        def service_name(self):
            return self.__service_name

        @service_name.setter
        def service_name(self, value):
            try:
                self.__service_name = value['name']
            except KeyError as ke:
                print(f"KeyError: 'name' not found in services json for this service. {ke}")
                exit()

        @property
        def service_type(self):
            return self.__service_type

        @service_type.setter
        def service_type(self, value):
            try:
                self.__service_type = value['type']
            except KeyError as ke:
                print(f"KeyError: 'type' not found in services json for this service. {ke}")
                exit()

        @property
        def service_short_services_url(self):
            return self.__service_short_services_url

        @service_short_services_url.setter
        def service_short_services_url(self, value):
            self.__service_short_services_url = f"services/{self.service_name}.{self.service_type}"

        def __str__(self):
            """
            Overriding the __str__ builtin to control the appearance of the object print-out for readability.
            :return: string
            """
            return f"SERVICE: {self.service_name}-->\n\ttype = {self.service_type}\n\tfolder = {self.folder}"

    # FUNCTIONS
    def create_params_for_request(token_action=None, json_payload=None, response_format="json"):
        """
        Create parameters to be submitted with the request.
        Various styles of requests are made and this function handles the variety and returns a dictionary
        :param token_action: route to be taken when creating the parameters
        :param json_payload: dictionary that will be added to basic json parameters
        :param response_format: type of response from requests, json and csv are two examples
        :return: dictionary of parameters
        """
        if token_action is None and json_payload is None:
            values = {'f': response_format}
        elif token_action == "getToken":
            values = {'username': USERNAME, 'password': PASSWORD, 'client': 'requestip', 'f': response_format}
        elif token_action is not None and json_payload is not None:
            values = {'token': token_action, 'f': response_format}
            values.update(json_payload)
        else:
            values = {'token': token_action, 'f': response_format}
        return values

    def create_master_url_list(objects_list):
        """
        Create a list of all urls using Folder objects and Service objects, stored in each Folder, and return the list.

        :param objects_list:  list of Folder objects, containing Service objects
        :return: list of strings that represent urls
        """
        master_list = []
        for obj_fold in objects_list:
            master_list.append(obj_fold.folder_short_services_url)
            for obj_serv in obj_fold.service_objects_list:
                master_list.append(obj_serv.service_short_services_url)
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
        Submit a request with parameters to a url and return the response.

        :param url: url to which to make a request
        :param params: parameters to accompany the request
        :return: response from request
        """
        # Protectionary action, to deal with mixed path characters between url syntax and os.path.join use of "\"
        url = url.replace("\\", "/")

        try:
            # Jessie discovered "verify" option and set to False to bypass the ssl issue
            response = requests.post(url=url, data=params, verify=False)
        except Exception as e:
            print("Error in response from requests: {}".format(e))
            exit()
        else:
            result = None
            try:
                if "html" in response.headers["Content-Type"]:
                    raise NotJSONException
                elif "text/csv" in response.headers["Content-Type"]:
                    result = response
                elif "application/json" in response.headers["Content-Type"]:
                    result = response.json()
            except json.decoder.JSONDecodeError as jde:
                print("Error decoding response to json: {}".format(jde))
                print(response)
                print(response.url)
                print(response.text)
                exit()
            except NotJSONException as NJE:
                print(f"Response appears to be html, not json.")
                print(response.url)
                print(response.headers)
                exit()
            return result

    def search_json_for_key(response_json, search_key):
        """Search json for a key of interest and return the found value or exit on Key or Type Error."""
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
        """Write content to a csv file."""
        with open(csv_path, 'w') as csv_file_handler:
            for line in response.text:
                csv_file_handler.write(line)
        return

    # FUNCTIONALITY
    #   Need a machine to which to make a request. Select at random from 4 total since we are bypassing web adaptor.
    machine = SERVER_MACHINE_NAMES[create_random_int(upper_integer=len(SERVER_MACHINE_NAMES))]

    #   Need a token to make secure requests
    root_server_url = SERVER_ROOT_URL.format(machine_name=machine, port=SERVER_PORT_SECURE)
    generate_token_url = os.path.join(root_server_url, AdminObject.GENERATE_TOKEN_ENDING)
    token_params = create_params_for_request(token_action="getToken")
    token_response = get_response(url=generate_token_url, params=token_params)
    token = search_json_for_key(response_json=token_response, search_key="token")

    #   Create a machine object for the selected ArcGIS Server machine. To store related values in object. Folders
    #       variable assigned below
    machine_object = MachineObject(machine_name=machine,
                                   root_url=root_server_url,
                                   security_token=token)

    #   Need to make a secure request for response as JSON to be able to access folders and services details
    basic_secure_params = create_params_for_request(token_action=machine_object.token)
    admin_object = AdminObject(root_machine_url=root_server_url)
    folders_request_response = get_response(url=admin_object.admin_services_url, params=basic_secure_params)

    #   Need folder names list and to clean list; Remove System & Utilities, & append entry for root folder, per Jessie
    #   NOTE: Noticed that Jessie also included 'GeoprocessingServices', but did not in statusdashboard script
    folder_names_raw = search_json_for_key(response_json=folders_request_response, search_key="folders")
    remove_folders = ["System", "Utilities", "GeoprocessingServices"]
    folder_names_clean = list(set(folder_names_raw) - set(remove_folders))
    folder_names_clean.append("")
    folder_names_clean.sort()

    #   Assign the folder names list to the machine object variable.
    machine_object.folder_names_list = folder_names_clean
    print(machine_object)

    #   Need a single list containing all folder url's AND all service url's from within all of those folders.
    #   It is passed to the server and indicates the resourceURIs for which metrics will be built in the query process
    #   Uses Folder objects to store folder urls and Service objects containing urls
    list_of_folder_objects = [FolderObject(name=folder_name, root_machine_url=machine_object.root_url) for folder_name
                              in machine_object.folder_names_list]

    #   For each folder, need a list of service objects for services in that folder
    for fold_obj in list_of_folder_objects:

        # Need a url to which to make a request to learn the services within
        services_request_response = get_response(url=fold_obj.folder_machine_url, params=basic_secure_params)
        services_json = search_json_for_key(response_json=services_request_response, search_key="services")

        # Need to store the inventory of services that are within each folder
        for service in services_json:
            service_object = ServiceObject(folder=fold_obj.name,
                                           service_json=service,
                                           root_machine_url=machine_object.root_url)
            fold_obj.service_objects_list.append(service_object)

    master_url_list = create_master_url_list(list_of_folder_objects)

    # Need to create a new report object for use in generating report on server.
    report_object = ReportObject(root_machine_url=machine_object.root_url,
                                 master_urls_list=master_url_list,
                                 basic_request_json=basic_secure_params)

    # Report is created on the server. No response is needed. The variable isn't used afterward for that reason.
    print("Creating Report")
    usage_report_params = create_params_for_request(token_action=machine_object.token,
                                                    json_payload=report_object.report_json_params)
    get_response(url=report_object.report_url_create, params=usage_report_params)

    # Need to get the report contents using the query url
    # NOTE: Like the 'usagereports' dictionary it appears that any dictionary 'value' that is a dictionary must be
    #   converted to a string first; using json.dumps()
    print("Querying Report")
    post_data_query = {'filter': json.dumps({'machines': '*'})}
    report_query_params = create_params_for_request(token_action=machine_object.token,
                                                    json_payload=post_data_query,
                                                    response_format='csv')
    report_query_response = get_response(url=report_object.report_url_query, params=report_query_params)

    # Need to write the report content to csv file
    print("Writing CSV")
    write_response_to_csv(response=report_query_response, csv_path=CSV_OUTPUT_FILE_PATH)

    # Need to delete the report from the server to reduce bloat
    print("Deleting Report")
    get_response(url=report_object.report_url_delete, params=basic_secure_params)

    print("Complete!")


if __name__ == "__main__":
    main()
