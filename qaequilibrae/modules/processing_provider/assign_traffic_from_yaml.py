import importlib.util as iutil
import sys
import textwrap

from datetime import datetime as dt

from qgis.core import QgsProcessingAlgorithm, QgsProcessingMultiStepFeedback, QgsProcessingParameterFile
from qgis.core import QgsProcessingParameterDefinition, QgsProcessingParameterBoolean

from qaequilibrae.i18n.translate import trlt


class TrafficAssignYAML(QgsProcessingAlgorithm):

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterFile(
                "conf_file",
                self.tr("Configuration file (.yaml)"),
                behavior=QgsProcessingParameterFile.File,
                fileFilter="",
                defaultValue=None,
            )
        )
        
        advparams = [
            QgsProcessingParameterBoolean(
            "datetime_to_resultname", 
            self.tr("Include current datetime to result name"), 
            defaultValue=True
            )
        ]
        
        for param in advparams:
            param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
            self.addParameter(param)

    def processAlgorithm(self, parameters, context, model_feedback):
        feedback = QgsProcessingMultiStepFeedback(5, model_feedback)

        # Checks if we have access to aequilibrae library
        if iutil.find_spec("aequilibrae") is None:
            sys.exit(self.tr("AequilibraE module not found"))

        from aequilibrae.paths import TrafficAssignment, TrafficClass
        from aequilibrae.project import Project
        from aequilibrae.matrix import AequilibraeMatrix
        import yaml

        feedback.pushInfo(self.tr("Getting parameters from YAML"))
        pathfile = parameters["conf_file"]
        with open(pathfile, "r") as f:
            params = yaml.safe_load(f)
        feedback.pushInfo(" ")
        feedback.setCurrentStep(1)

        feedback.pushInfo(self.tr("Opening project"))
        # Opening project
        project = Project()
        project.open(params["project"])

        # Creating graph
        project.network.build_graphs()

        # Creating traffic classes
        traffic_classes = []
        feedback.pushInfo(self.tr("{} traffic classes have been found").format(len(params["traffic_classes"])))
        select_links = "select_links" in params and params["select_links"]
        if select_links:
            selection_dict = {}
            for selections in params["select_links"]:
                for name in selections:
                    link_list = ''
                    for text in selections[name]:
                        link_list = link_list + ',' + text
                    link_list = ('[' + link_list[1:] + ']')
                    link_list=eval(link_list)
                    selection_dict[name] = link_list

        for classes in params["traffic_classes"]:
            for traffic in classes:

                # Getting matrix
                demand = AequilibraeMatrix()
                demand.load(classes[traffic]["matrix_path"])
                demand.computational_view([classes[traffic]["matrix_core"]])

                # Getting graph
                graph = project.network.graphs[classes[traffic]["network_mode"]]
                graph.set_graph(params["assignment"]["time_field"])
                if str(classes[traffic]["blocked_centroid_flows"])=="True":
                    graph.set_blocked_centroid_flows(True)
                else:
                    graph.set_blocked_centroid_flows(False)

                if "skims" in classes[traffic] and classes[traffic]["skims"]:
                    skims = [sk.strip() for sk in classes[traffic]["skims"].split(",")]
                    graph.set_skimming(skims)

                # Setting class
                assigclass = TrafficClass(name=traffic, graph=graph, matrix=demand)
                assigclass.set_pce(classes[traffic]["pce"])

                if "fixed_cost" in classes[traffic] and classes[traffic]["fixed_cost"]:
                    if isinstance(classes[traffic]["vot"], (int, float)):
                        assigclass.set_fixed_cost(classes[traffic]["fixed_cost"])
                        assigclass.set_vot(classes[traffic]["vot"])
                    else:
                        sys.exit("error: fixed_cost must come with a correct value of time")
                
                # Adding select links analysis
                if select_links :
                    assigclass.set_select_links(selection_dict)

                # Adding class
                feedback.pushInfo(f"\t- {traffic} ' ' {str(classes[traffic])}")

                traffic_classes.append(assigclass)
        feedback.pushInfo(" ")
        feedback.setCurrentStep(2)

        # Setting up assignment
        feedback.pushInfo(self.tr("Setting up assignment"))
        feedback.pushInfo(str(params["assignment"]))

        assig = TrafficAssignment()
        assig.set_classes(traffic_classes)
        assig.set_vdf(params["assignment"]["vdf"])
        assig.set_vdf_parameters({"alpha": params["assignment"]["alpha"], "beta": params["assignment"]["beta"]})
        assig.set_capacity_field(params["assignment"]["capacity_field"])
        assig.set_time_field(params["assignment"]["time_field"])

        assig.set_algorithm(params["assignment"]["algorithm"])
        assig.max_iter = params["assignment"]["max_iter"]
        assig.rgap_target = params["assignment"]["rgap"]

        feedback.pushInfo(" ")
        feedback.setCurrentStep(3)

        # Running assignment
        feedback.pushInfo(self.tr("Running assignment"))
        assig.execute()
        feedback.pushInfo(" ")
        feedback.setCurrentStep(4)

        # Saving outputs
        feedback.pushInfo(self.tr("Saving outputs"))
        feedback.pushInfo(str(assig.report()))
        if str(parameters["datetime_to_resultname"])=="True":
            params["result_name"]=(params["result_name"]+dt.now().strftime("_%Y-%m-%d_%Hh%M"))
        assig.save_results(params["result_name"])
        assig.save_skims(params["result_name"], which_ones="all", format="aem")
        if select_links:
            assig.procedure_id = assig.procedure_id+"_S"
            assig.save_select_link_results(params["result_name"])
        feedback.pushInfo(" ")
        feedback.setCurrentStep(5)

        project.close()

        return {"Output": "Traffic assignment successfully completed"}

    def name(self):
        return self.tr("Traffic assignment from file")

    def displayName(self):
        return self.tr("Traffic assignment from file")

    def group(self):
        return ("03-"+self.tr("Paths and assignment"))

    def groupId(self):
        return ("03-"+self.tr("Paths and assignment"))

    def shortHelpString(self):
        return textwrap.dedent("\n".join([self.string_order(1), self.string_order(2), self.string_order(3)]))

    def createInstance(self):
        return TrafficAssignYAML()

    def string_order(self, order):
        if order == 1:
            return self.tr("Run a traffic assignment using a YAML configuration file.")
        elif order == 2:
            return self.tr("Example of valid configuration file:")
        elif order == 3:
            return textwrap.dedent("""\
                project: D:/AequilibraE/Project/
                result_name: sce_from_yaml
                traffic_classes:
                    - car:
                        matrix_path: D:/AequilibraE/Project/matrices/demand.aem
                        matrix_core: car
                        network_mode: c
                        pce: 1
                        blocked_centroid_flows: True
                        skims: travel_time, distance
                    - truck:
                        matrix_path: D:/AequilibraE/Project/matrices/demand.aem
                        matrix_core: truck
                        network_mode: c
                        pce: 2
                        fixed_cost: toll
                        vot: 12
                        blocked_centroid_flows: True
                assignment:
                    algorithm: bfw
                    vdf: BPR2
                    alpha: 0.15
                    beta: power
                    capacity_field: capacity
                    time_field: travel_time
                    max_iter: 250
                    rgap: 0.00001
                select_links: #optionnal, name with a list of tuples as [(link_id, link_direction)]
                    - survey_site_1: [(23,0)]
                    - est-west-transit: [(12, 1),(402, 1)]
                """)

    def tr(self, message):
        return trlt("TrafficAssignYAML", message)
