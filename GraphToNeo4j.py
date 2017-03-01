#This file must be contained in the import folder on the machine running
#Neo4j. Otherwise, the user must change the configurations setting in
#conf/neo4j.conf
import json
import csv
import pandas as pd
import os
import sys
import logging
import argparse
import tempfile
from py2neo import Graph, authenticate

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Preconstructed queries
entityNodeQuery = """
    USING PERIODIC COMMIT 1000
    LOAD CSV WITH HEADERS FROM "file://%s" AS dvs
    WITH dvs WHERE NOT dvs.concreteType = "org.sagebionetworks.repo.model.provenance.Activity"
       MERGE (entity:Entity {id:dvs._id}) ON CREATE
       SET entity = dvs
"""
activityNodeQuery = """
    USING PERIODIC COMMIT 1000
    LOAD CSV WITH HEADERS FROM "file://%s" AS dvs
    WITH dvs WHERE dvs.concreteType = "org.sagebionetworks.repo.model.provenance.Activity"
       MERGE (activity:Activity {id:dvs._id}) ON CREATE
       SET activity = dvs
"""
generatedByEdgeQuery = """
    USING PERIODIC COMMIT 1000
    LOAD CSV WITH HEADERS FROM "file://%s" AS erow
    WITH erow WHERE erow._label = "generatedBy"
    MATCH (in_node:Entity { _id:erow._inV })
    MATCH (out_node:Activity { _id:erow._outV })
    MERGE (out_node)-[:GENERATED_BY { action:erow._label, id:erow._id }]->(in_node)
"""
usedEdgeQuery = """
    USING PERIODIC COMMIT 1000
    LOAD CSV WITH HEADERS FROM "file://%s" AS erow
    WITH erow WHERE erow._label = "used"
    MATCH (in_node:Activity { _id:erow._inV })
    MATCH (out_node:Entity { _id:erow._outV })
    MERGE (out_node)-[:USED { action:erow._label, id:erow._id, wasExecuted:erow.wasExecuted }]->(in_node)
"""
executedEdgeQuery = """
    USING PERIODIC COMMIT 1000
    LOAD CSV WITH HEADERS FROM "file://%s" AS erow
    WITH erow WHERE erow._label = "executed"
    MATCH (in_node:Activity { _id:erow._inV })
    MATCH (out_node:Entity { _id:erow._outV })
    MERGE (out_node)-[:EXECUTED { action:erow._label, id:erow._id, wasExecuted:erow.wasExecuted }]->(in_node)
"""

nodeQueries = [entityNodeQuery, activityNodeQuery]

edgeQueries = [generatedByEdgeQuery, usedEdgeQuery, executedEdgeQuery]

def json2neo4j(jsonfilename, graph, node_queries = nodeQueries, edge_queries = edgeQueries):
    # Retrieve JSON/CSV file
    logger.info('Creating temporary JSON/CSV file')
    nodes = tempfile.NamedTemporaryFile(prefix='vertices', suffix='.csv')
    edges = tempfile.NamedTemporaryFile(prefix='edges', suffix='.csv')

    # dir_info = os.stat('.')
    # uid = dir_info.st_uid
    # gid = dir_info.st_gid

    logger.info('Converting %s to CSV' % jsonfilename)
    with open(jsonfilename) as json_file:
        JSON = json.load(json_file)

    df1 = pd.DataFrame(JSON['vertices'])
    if 'used' in df1.columns:
        df1 = df1.drop('used', 1)
    if 'description' in df1.columns:
        df1 = df1.drop('description', 1)
    df1.to_csv(nodes.name, index=False)
    # index=False removes first column with null header

    df2 = pd.DataFrame(JSON['edges'])
    if df2.empty:
        logger.info('No edges/activities/provenance in graph')

        # Change file permission and ownership for Neo4j
        # os.chown(nodes.name, uid, gid)

        # Add uniqueness constraints and indexing
        graph.run("CREATE CONSTRAINT ON (entity:Entity) ASSERT entity.id IS UNIQUE")
        graph.run("CREATE INDEX ON :Entity(entity)")
        for nodeQuery in node_queries:
            nodeQuery = nodeQuery % nodes.name

        #Send Cypher query
        logger.info('Loading data from CSV file(s) to Neo4j')
        graph.run(nodeQuery[0])

        graph.run("DROP CONSTRAINT ON (entity:Entity) ASSERT entity.id IS UNIQUE")
        graph.run("MATCH (n) WHERE n:Entity REMOVE n.id").evaluate()

        # Clean up directory and remove created files
        # Comment out if you would like to keep csv files
        logger.debug('Removing csv files from local directory')
        nodes.close()

    else:
        print df2
        df2.to_csv(edges.name, index=False)

        # Change file permission and ownership for Neo4j
        # os.chown(nodes.name, uid, gid)
        # os.chown(edges.name, uid, gid)

        # Add uniqueness constraints and indexing
        logger.info('Establishing uniqueness constraints and indexing for Neo4j')
        graph.run("CREATE CONSTRAINT ON (entity:Entity) ASSERT entity.id IS UNIQUE")
        graph.run("CREATE CONSTRAINT ON (activity:Activity) ASSERT activity.id IS UNIQUE")
        graph.run("CREATE INDEX ON :Entity(entity)")

        # Build query
        logger.info('Loading data from CSV file(s) to Neo4j')
        for nodeQuery in node_queries:
            nodeQuery = nodeQuery % nodes.name
            graph.run(nodeQuery)
        for edgeQuery in edge_queries:
            edgeQuery = edgeQuery % edges.name
            graph.run(edgeQuery)

        # Send Cypher query
        logger.info('Loading data from CSV file(s) to Neo4j')
        # for nodeQuery in node_queries:
        #     graph.run(nodeQuery)
        # for edgeQuery in edge_queries:
        #     graph.run(edgeQuery)
        graph.run("DROP CONSTRAINT ON (entity:Entity) ASSERT entity.id IS UNIQUE")
        graph.run("DROP CONSTRAINT ON (activity:Activity) ASSERT activity.id IS UNIQUE")
        graph.run("MATCH (n) WHERE n:Activity OR n:Entity REMOVE n.id").evaluate()

        # Clean up directory and remove created files
        # Comment out if you would like to keep csv files
        logger.debug('Removing csv files from local directory')
        nodes.close()
        edges.close()