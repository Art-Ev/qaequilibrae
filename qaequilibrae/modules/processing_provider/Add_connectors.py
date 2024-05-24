import importlib.util as iutil
import sys
from qgis.core import QgsProcessingMultiStepFeedback
from qgis.core import QgsProcessingParameterFile, QgsProcessingParameterNumber, QgsProcessingParameterString
from qaequilibrae.modules.common_tools import standard_path

from .translatable_algo import TranslatableAlgorithm


class AddConnectors(TranslatableAlgorithm):

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterNumber(
                "nb_conn",
                self.tr("Connectors per centroid"),
                type=QgsProcessingParameterNumber.Integer,
                minValue=1,
                maxValue=10,
                defaultValue=1,
            )
        )
        self.addParameter(
            QgsProcessingParameterString(
                "mode", self.tr("Modes to connect (only one at a time)"), multiLine=False, defaultValue="c"
            )
        )
        self.addParameter(
            QgsProcessingParameterFile(
                "PrjtPath",
                self.tr("Project path"),
                behavior=QgsProcessingParameterFile.Folder,
                defaultValue=standard_path(),
            )
        )

    def processAlgorithm(self, parameters, context, model_feedback):
        feedback = QgsProcessingMultiStepFeedback(2, model_feedback)

        # Checks if we have access to aequilibrae library
        if iutil.find_spec("aequilibrae") is None:
            sys.exit(self.tr("AequilibraE not found"))

        from aequilibrae import Project

        feedback.pushInfo(self.tr("Connecting to AequilibraE project"))
        project = Project()
        project.open(parameters["PrjtPath"])

        all_nodes = project.network.nodes
        nodes_table = all_nodes.data

        feedback.pushInfo(" ")
        feedback.setCurrentStep(1)

        # Adding connectors
        nb_conn = parameters["nb_conn"]
        mode = parameters["mode"]
        feedback.pushInfo(self.tr('Adding {} connectors when none exists for mode "{}"').format(nb_conn, mode))
        for idx, node in nodes_table.query("is_centroid == 1").iterrows():
            curr = all_nodes.get(node.node_id)
            curr.connect_mode(curr.geometry.buffer(0.01), mode_id=mode, connectors=nb_conn)
        feedback.pushInfo(" ")
        feedback.setCurrentStep(2)

        project.close()
        output_file = parameters["PrjtPath"]
        return {"Output": output_file}

    def name(self):
        return self.tr("Add centroid connectors")

    def displayName(self):
        return self.tr("Add centroid connectors")

    def group(self):
        return self.tr("Model Building")

    def groupId(self):
        return self.tr("Model Building")

    def shortHelpString(self):
        return self.tr("Go through all the centroids and add connectors only if none exists for the chosen mode")

    def createInstance(self):
        return AddConnectors(self.tr)
