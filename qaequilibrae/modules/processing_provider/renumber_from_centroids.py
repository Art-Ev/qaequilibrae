from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject
from qgis.core import QgsProcessing, QgsProcessingMultiStepFeedback
from qgis.core import QgsProcessingParameterVectorLayer, QgsProcessingParameterField, QgsProcessingParameterFile

import importlib.util as iutil
import pandas as pd
import sys
from shapely.wkt import loads as load_wkt
from qaequilibrae.modules.common_tools import standard_path

from .translatableAlgo import TranslatableAlgorithm


class RenumberFromCentroids(TranslatableAlgorithm):

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                "nodes", self.tr("Centroids"), types=[QgsProcessing.TypeVectorPoint], defaultValue="nodes"
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                "node_id",
                self.tr("Zone ID"),
                type=QgsProcessingParameterField.Numeric,
                parentLayerParameterName="nodes",
                allowMultiple=False,
                defaultValue="node_id",
            )
        )
        self.addParameter(
            QgsProcessingParameterFile(
                "PrjtPath",
                self.tr("Output folder"),
                behavior=QgsProcessingParameterFile.Folder,
                defaultValue=standard_path(),
            )
        )

    def processAlgorithm(self, parameters, context, model_feedback):
        feedback = QgsProcessingMultiStepFeedback(3, model_feedback)

        # Checks if we have access to aequilibrae library
        if iutil.find_spec("aequilibrae") is None:
            sys.exit(self.tr("AequilibraE not found"))

        from aequilibrae import Project

        feedback.pushInfo(self.tr("Connecting to aequilibrae project"))
        project = Project()
        project.open(parameters["PrjtPath"])
        feedback.pushInfo(" ")
        feedback.setCurrentStep(1)

        feedback.pushInfo(self.tr("Importing node layer from QGIS"))
        layer_crs = self.parameterAsVectorLayer(parameters, "nodes", context).crs()
        aeq_crs = QgsCoordinateReferenceSystem("EPSG:4326")

        # Import QGIS layer as a panda dataframe
        layer = self.parameterAsVectorLayer(parameters, "nodes", context)
        columns = [f.name() for f in layer.fields()] + ["geometry"]
        columns_types = [f.typeName() for f in layer.fields()]  #

        def fn(f):
            geom = f.geometry()
            geom.transform(QgsCoordinateTransform(layer_crs, aeq_crs, QgsProject.instance()))
            return dict(zip(columns, f.attributes() + [geom.asWkt()]))

        row_list = [fn(f) for f in layer.getFeatures()]
        df = pd.DataFrame(row_list, columns=columns)
        feedback.pushInfo(" ")
        feedback.setCurrentStep(2)

        feedback.pushInfo(self.tr("Looking for existing nodes from AequilibraE project"))
        # Import QGIS layer as a panda dataframe
        all_nodes = project.network.nodes
        nodes_table = all_nodes.data

        def format_XY(geometry):
            formated = (
                str(round(float(str(geometry)[7:-1].split(" ")[0]), 8))
                + "_"
                + str(round(float(str(geometry)[7:-1].split(" ")[1]), 8))
            )
            return formated

        feedback.pushInfo(self.tr("Comparing nodes from input centroid layer:"))
        # to be able to compare, rounding of coordinates to a sufficient degree of accuracy... 1mm
        df["XY"] = df.apply(lambda row: format_XY(row.geometry), axis=1)
        feedback.pushInfo(str(df.XY.head(5)))
        feedback.pushInfo(self.tr("With existing nodes in AequilibraE project:"))
        nodes_table["XY"] = nodes_table.apply(lambda row: format_XY(row.geometry), axis=1)
        feedback.pushInfo(str(nodes_table.XY.head(5)))
        feedback.pushInfo(" ")

        find = 0
        create = 0
        fail = 0
        for idx, zone in df.iterrows():
            matching = nodes_table[(nodes_table.XY == zone.XY)]
            if len(matching.index) == 1:
                find += 1
                if int(zone[parameters["node_id"]]) != int(matching["node_id"].iloc[0]):
                    updt = all_nodes.get(matching["node_id"].iloc[0])
                    updt.is_centroid = 1
                    updt.renumber(zone[parameters["node_id"]])
                    updt.save()
            elif len(matching.index) == 0:
                create += 1
                new = all_nodes.new_centroid(zone[parameters["node_id"]])
                new.geometry = load_wkt(zone["geometry"])
                new.save()
            elif len(matching.index) > 1:
                fail += 1
                feedback.pushInfo(
                    self.tr(" Multiple nodes found for zone ")
                    + str(zone[parameters["node_id"]])
                    + self.tr(", unable to decide which node to use")
                )
        feedback.pushInfo(self.tr("{} zones found in input layer: ").format(df.shape[0]))
        if find > 0:
            feedback.pushInfo(self.tr("    {} zones found an existing matching node").format(find))
        if create > 0:
            feedback.pushInfo(self.tr("    {} new nodes added for unmatched zones").format(create))
        if fail > 0:
            feedback.pushInfo(self.tr("    {} zones could not be processed").format(fail))
        feedback.pushInfo(" ")

        project.close()
        del row_list, df

        output_file = parameters["PrjtPath"]
        return {"Output": output_file}

    def name(self):
        return self.tr("Nodes from centroid")

    def displayName(self):
        return self.tr("Nodes from centroid")

    def group(self):
        return self.tr("Model Building")

    def groupId(self):
        return self.tr("Model Building")

    def shortHelpString(self):
        return self.tr(
            """
        Import or create nodes to match an AequilibraE project with a GIS layer of centroids
        Warning : you may have to change existing node_id (ex. using QGIS field calculator) to ensure that changed node IDs (coming from zone id) are not already used.
        """
        )

    def createInstance(self):
        return RenumberFromCentroids(self.tr)
