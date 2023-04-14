# Apache Iceberg

<!-- vim-markdown-toc GFM -->

* [Brief description](#brief-description)
* [Licensing / pricing model](#licensing--pricing-model)
* [Project Maturity](#project-maturity)
    * [Open Format Specification](#open-format-specification)
    * [Java Libraries](#java-libraries)
    * [Pyiceberg](#pyiceberg)
* [What Are the Goals of Iceberg?](#what-are-the-goals-of-iceberg)
    * [Serializable isolation](#serializable-isolation)
    * [Speed](#speed)
    * [Scale](#scale)
    * [Evolution](#evolution)
    * [Dependable Types](#dependable-types)
    * [Storage Separation](#storage-separation)
    * [Formats](#formats)
* [Main components](#main-components)
    * [Iceberg Table Specification](#iceberg-table-specification)
    * [Catalog Service](#catalog-service)
* [Integrations](#integrations)
    * [Spark](#spark)
        * [Structured streaming](#structured-streaming)
    * [Hive](#hive)
* [Comparison with other data lake filesystems](#comparison-with-other-data-lake-filesystems)
    * [Iceberg vs Delta](#iceberg-vs-delta)
        * [Maturity](#maturity)
        * [Unique to Iceberg](#unique-to-iceberg)
            * [Concurrent Writes to Same Table](#concurrent-writes-to-same-table)
            * [Partition Layout Evolution](#partition-layout-evolution)
        * [Common to Both](#common-to-both)
            * [ACID transactions](#acid-transactions)
        * [Time Travel/Version Rollback](#time-travelversion-rollback)
* [Starting simple](#starting-simple)
* [Scalable Production](#scalable-production)
* [Draft of a deployment design](#draft-of-a-deployment-design)
* [Working examples](#working-examples)
* [Reference](#reference)

<!-- vim-markdown-toc -->

## Brief description

> Iceberg is a high-performance format for huge analytic tables. Iceberg brings the reliability and simplicity of SQL tables to big data, while making it possible for engines like Spark, Trino, Flink, Presto, Hive and Impala to safely work with the same tables, at the same time.

Essentially Iceberg has three components, all versioned separately:
* [Open format specification](https://iceberg.apache.org/spec/) for a table level persistence store
* Java API Layer & Reference implementation for interacting with the format specification, and integrating with processing engines (in-tree: Spark, Flink & Hive)
* Python API layer & CLI to interact with the Catalog server (or its Glue/Hive/DynamoDB equivalent (?)), and direct querying of the metadata/data layers

Other processing engines have their own out-of-tree integrations with Iceberg (AWS Glue, Presto, Trino, Impala). Snowflake have released support for Iceberg Tables as a open-standard alternative to their proprietary table format to [public preview](https://www.snowflake.com/blog/iceberg-tables-powering-open-standards-with-snowflake-innovations/).

## Licensing / pricing model

Originally developed by Netflix, released to the public domain in 2017, donated to Apache Foundation in 2018. Released under the [Apache License 2.0](https://github.com/apache/iceberg/blob/master/LICENSE)

## Project Maturity

### Open Format Specification

Version 1 and 2 of the format specification have been completed and adopted by the community. The two releases see to be additive in scope.

### Java Libraries

Apache Iceberg v1.0 was released in November 2022.

### Pyiceberg

Pyiceberg is versioned separately despite being part of the Iceberg git repository, and is yet to have a major release (version 0.13 at time of writing).

## What Are the Goals of Iceberg?

### Serializable isolation

> Reads will be isolated from concurrent writes and always use a committed snapshot of a table’s data. Writes will support removing and adding files in a single operation and are never partially visible. Readers will not acquire locks.

Essentially what this means in practice is that, Iceberg supports writes to (immutable) files in the directory structure of the data layer without the contents being registered in the table entity. Iceberg terms this Optimistic Concurrency; any table data or metadata is created optimistically assuming that the current "version" will not be changed before that write is committed. In the case of multiple concurrent writes, the first to win the race succeeds, all others have to be retried.

When the write is committed, the table state is changed (i.e. the new data files previously written are registered against the tables) a new (immutable) metadata file is created, and the pointer held by the catalog service is swapped atomically.

> An atomic swap of one table metadata file for another provides the basis for serializable isolation. Readers use the snapshot that was current when they load the table metadata and are not affected by changes until they refresh and pick up a new metadata location.

If the metadata (or specifically the list of snapshots, see the next section for more detail) is no longer concurrent (i.e. does not have the same state as the one fetched when the write began) at point of commit, the writer process must recalculate the new metadata state against the current version, and try to commit this change again. How difficult this is depends on the change being written, and the isolation level which it requires, and is out of scope of this article.

### Speed

> Operations will use O(1) remote calls to plan the files for a scan and not O(n) where n grows with the size of the table, like the number of partitions or files.

The metadata files I mentioned earlier contain all metadata relating to the table schema, partitioning config, custom properties, and snapshots (i.e. table states) of the table contents. This means that a single source of truth is maintained for query planning.

### Scale

> Job planning will be handled primarily by clients and not bottleneck on a central metadata store. Metadata will include information needed for cost-based optimization.

This point is already mostly covered with what I've said above; the metadata required for query planning is referenced by a pointer to a metadata file in the object store, the onus is on clients to use this for query planning before submission of the query to whatever distributed compute is available.

### Evolution

> Tables will support full schema and partition spec evolution. Schema evolution supports safe column add, drop, reorder and rename, including in nested structures.

Schema in this context is the table schema, the names and types of field stored in a table. Importantly, the relationship between tables and schemas is one-to-many, i.e. a table is described by an iterable of schemas. When a new schema is added, this evolution process copies the previous schema, applies the changes, and adds this (immutable) schema to the list of schemas recorded against the table. This gives a full history of how the table structure has evolved over time.

<!-- Exactly how you're allowed to change a schema seems fairly open, but there are notable exceptions. -->

<!-- Valid schema evolutions are: -->
<!-- * Type promotion (only when it increases field precision) -->
<!-- * Field addition -->
<!-- * Field rename -->
<!-- * Field reordering -->
<!-- * Field deletion -->

<!-- Invalid schema evolutions are -->
<!-- * Grouping of structs (nested -->
<!-- Schema evolution is provided  -->

See [Storage Separation](#storage-separation) for more information on partition evolution.

### Dependable Types

> Tables will provide well-defined and dependable support for a core set of types.

Iceberg fields can be of primitive type (type wrapper around commonly used Avro/Parquet/Orc primitive types), or can be of struct type (immutable tuple of fields, think of it as a typed dict with metadata around default value/nullability/comments). Iceberg has its own types and its own mappings between these types and the types of the underlying (Avro/Parquet/ORC) representation.

### Storage Separation

> Partitioning will be table configuration. Reads will be planned using predicates on data values, not partition values. Tables will support evolving partition schemes.

Partitions are referenced by the top-level table metadata entity (Iceberg calls this a Specification), which also refers to the schemas iterable I mentioned previously. Partitions are applied against a data file, and what's different about Icebergs approach to partitioning is that the partition can represent the result of a transform applied to the data, instead of being limited to the data itself. This can be used to store the result of common filter operations against the data to avoid recomputing.
<!-- recomputing the values of common operations if that operation has a partition stored against its outputs.  -->

Importantly this means that new partitions can be added without the overhead of adding new fields solely for demarcating partitions, and without the need for querying a partition column explicitly. For example if you have a timestamp column you want to partition by month, you can add a column against a transform that extracts the month from that column rather than needing to extract the month into its own partition column, and utilize the partitioning when querying the timestamp column directly rather than needing to incorporating the extracted month column into the query explicitly. This ability to utilize partitions without knowing their exact structure is what Iceberg calls Hidden Partitioning.

These partition transforms can evolve with time to become more granular whilst still being applicable to the previous use case. The partitioning scheme of a table to be changed without requiring a rewrite of the table; the old data will follow the old partition, new data will follow the new partition, and Iceberg will be made aware in order to plan queries appropriately.
Queries can be optimised using multiple partitions schemes (data partitioned using different schemes will be planned separately to maximize performance).

### Formats

> Underlying data file formats will support identical schema evolution rules and types. Both read-optimized and write-optimized formats will be available.

Iceberg operates on top of a distributed file system with data (Avro, Parquet & ORC) and metadata (Avro) stored in common open formats. Iceberg maps its own built-in types to theirs.

<!-- ### Format Specification -->

<!-- ## -->

<!-- #### Schema evolution -->
<!--     supports add, drop, update, or rename, and has no side-effects -->

<!-- #### Hidden Paritioning -->
<!--     Hidden partitioning prevents user mistakes that cause silently incorrect results or extremely slow queries -->

<!-- #### Parition Layout Evolution -->
<!--     Partition layout evolution can update the layout of a table as data volume or query patterns change -->

<!-- #### Time Travel -->
<!--     Time travel enables reproducible queries that use exactly the same table snapshot, or lets users easily examine changes -->

<!-- #### Version Rollback -->
<!--     Version rollback allows users to quickly correct problems by resetting tables to a good state -->

<!-- ### Catalog -->

<!-- ### pyiceberg -->

## Main components

The envisioned architecture is detailed in the follow graphic ![Graphic detailing target architecture of Iceberg.](https://iceberg.apache.org/img/iceberg-metadata.png)

This graphic describes a single stateful service (Catalog), which operates on the file store directly in the metadata/data layers.

### Iceberg Table Specification

Iceberg was designed to run completely abstracted from physical storage using object storage. All locations are “explicit, immutable, and absolute” as defined in metadata

All data and metadata files are immutable, row-level deletion is handled by creating new metadata files listing deletes rather than rewriting the existing data files.

Digging into this we can see that the state of the service is simply to hold a pointer to the latest table state in the form of a metadata file (swapped atomically)

### Catalog Service

Iceberg supports a variety of Catalog implementations:

* Iceberg's native REST Catalog
* JDBC Catalog
* Hive Catalog
* Spark Catalog
* AWS Glue Catalog
* DynamoDb Catalog

Regardless of the implementation, the goal of the catalog service is to provide the single-source-of-truth for metadata state; managing namespaces, partitioning, and updates to table state.

## Integrations

### Spark

Iceberg features full support for the following spark APIs
* Spark DataFrameWriterV2 API
* Spark DataFrameReader API
* Spark DataStreamWriter API
* Spark DataStreamReader API
* Spark DataSourceV2 API

#### Structured streaming

Iceberg supports both reading and writing Dataframes using Sparks native structured streaming API (`spark.readStream` and `spark.writeStream`) in analogy to Delta Live Tables. However, Iceberg doesn't yet include any explicit orchestration functionality for managing the resulting live tables. These streams are processed as microbatches

<!-- ### Nessie/LakeFS -->

<!-- Both Nessie and LakeFS support Iceberg as a backend. -->

### Hive

## Comparison with other data lake filesystems

### Iceberg vs Delta

#### Maturity

There is a vast difference in maturity between Iceberg and Delta. Arguably the functional scope of Iceberg is also larger, where the functional equivalents of Delta are part of the closed source Databricks ecosystem.

#### Unique to Iceberg

##### Concurrent Writes to Same Table

Iceberg supports concurrent writes to the same Delta table from multiple spark drivers natively, whereas Delta requires a [workaround using DynamoDB and explicit feature/version toggle on all LogStore writers](https://docs.delta.io/latest/delta-storage.html#-delta-storage-s3-multi-cluster)

##### Partition Layout Evolution

> Partition layout evolution can update the layout of a table as data volume or query patterns change

As described in [Storage Separation](#storage-separation) common query transformations can be implemented as partitions, reducing re-computation. Reading between the lines it feels like the goal is to have this as an adaptive component of Iceberg rather than relying on explicit implementation.

#### Common to Both

##### ACID transactions

ACID transactionality seems to be provided via the Catalog implementation. How exactly this works for the use case of direct comm Apache Hive (which is provided via built in to Iceberg)

#### Time Travel/Version Rollback

In Iceberg both data and metadata files are immutable, with any row level deletes being stored as separate files rather than overwriting the immutable data file. Any data updates will result in a new snapshot on commit. Any metadata updates are done with incremental ordering so state at any one moment in time is unambiguous. Time travel is possible to any point in time that has a snapshot associated, as that snapshot contains direct references to the immutable data files known to Iceberg (i.e. reflected in the table state) at that point in time.

In contrast, Delta stores incremental data changes as a delta in a transaction log. Time travel starts from the current states and reverts the changes described by the transaction log until arriving at the desired state.

<!-- #### Unique to Delta -->

<!-- ### Iceberg vs Apache Hive -->

<!-- https://www.dremio.com/resources/guides/apache-iceberg-an-architectural-look-under-the-covers/ -->

<!-- ## Limitations -->

<!-- >...large, slow-changing collection of files built on open formats over a distributed filesystem or key-value store -->

## Starting simple

```shell
git clone https://github.com/apache/iceberg.git
cd docker-spark-iceberg
docker-compose up
```

If we open `https://localhost:8888` we see an ipython notebook. Navigate to `Getting Started.ipynb` and select `Cell -> Run All`. You'll see a bunch of Java exceptions crop up
If we `docker-compose exec mc bash` and use the `mc` client to query the `s3` object store in the `minio` container, we see:

```shell
[root@644ea375ae1e /]# mc ls minio/warehouse/nyc/taxis/data
[2023-04-05 11:22:29 UTC]  33MiB STANDARD 00003-4-9c06b253-ce7a-46d6-8881-f4b4f74ac47b-00001.parquet
[2023-04-05 13:35:33 UTC]  37MiB STANDARD 00179-12-c9dc6133-47a9-4f3b-a060-8ae885f1875c-00001.parquet
[2023-04-05 14:48:15 UTC] 794KiB STANDARD 00183-215-4ec61c1b-b666-4302-95bc-2b1403e9448c-00001.parquet
[2023-04-05 14:48:17 UTC] 293KiB STANDARD 00185-417-dd21a05b-3591-41c7-ad7d-f7ed50853bf4-00001.parquet
```

So we have some data files

```shell
[root@644ea375ae1e /]# mc ls minio/warehouse/nyc/taxis/data
[2023-04-12 18:37:35 BST] 5.7KiB STANDARD 00000-314d91a6-0802-418f-979a-08fe0a900864.metadata.json
[2023-04-12 18:38:02 BST] 5.7KiB STANDARD 00000-baefca3c-3770-41c8-a4d7-d459d585c7c4.metadata.json
[2023-04-12 18:38:03 BST] 8.0KiB STANDARD 00001-295407cb-8d60-4de2-a344-bd2e8e7d0eb1.metadata.json
[2023-04-12 18:38:03 BST]  10KiB STANDARD 00002-e256f822-d925-4a26-99c1-d4bbd8e49d33.metadata.json
[2023-04-12 18:38:03 BST]  12KiB STANDARD 00003-0329e8e2-4969-46b7-8131-8cd99329d265.metadata.json
[2023-04-12 18:38:03 BST]  15KiB STANDARD 00004-9bb8ce02-2bab-4d46-a084-33d4edbaa919.metadata.json
[2023-04-12 18:38:03 BST]  17KiB STANDARD 00005-80f26258-9dc5-43e4-b823-10e1d37a8074.metadata.json
[2023-04-12 18:38:52 BST]  18KiB STANDARD 00006-67c61495-768d-445c-9e3a-a06d1ad67648.metadata.json
[2023-04-12 18:39:00 BST]  20KiB STANDARD 00007-85eb952d-e218-490b-8f7e-b9ffff965479.metadata.json
[2023-04-12 18:39:05 BST]  20KiB STANDARD 00008-b8a933cd-c9e2-405e-8697-979a9fa3399c.metadata.json
[2023-04-12 18:39:06 BST]  21KiB STANDARD 00009-03b9aaf6-26b0-4687-b7f9-18b8796ee56f.metadata.json
[2023-04-12 18:39:07 BST]  21KiB STANDARD 00010-1804bb48-de71-4bf9-98af-bbaa544e5b3a.metadata.json
[2023-04-12 18:38:02 BST] 7.1KiB STANDARD 250f2238-99fe-4d13-8e52-7a5a927c95b5-m0.avro
[2023-04-12 18:38:52 BST] 7.3KiB STANDARD 43c11397-55c7-479c-bbf6-205a4b18f17a-m0.avro
[2023-04-12 18:38:52 BST] 7.3KiB STANDARD 43c11397-55c7-479c-bbf6-205a4b18f17a-m1.avro
[2023-04-12 18:38:59 BST] 7.3KiB STANDARD 67312a96-2591-4049-a03c-3e308b6b4e74-m0.avro
[2023-04-12 18:38:59 BST] 7.2KiB STANDARD 67312a96-2591-4049-a03c-3e308b6b4e74-m1.avro
[2023-04-12 18:39:05 BST] 7.2KiB STANDARD 8b3afebb-a045-487a-b65c-8d9e8a44c5d0-m0.avro
[2023-04-12 18:39:05 BST] 7.2KiB STANDARD 8b3afebb-a045-487a-b65c-8d9e8a44c5d0-m1.avro
[2023-04-12 18:37:35 BST] 7.1KiB STANDARD 9dc86170-01c3-4570-ac05-3339c987738a-m0.avro
[2023-04-12 18:39:00 BST] 3.7KiB STANDARD snap-1509695290243621361-1-67312a96-2591-4049-a03c-3e308b6b4e74.avro
[2023-04-12 18:37:35 BST] 3.7KiB STANDARD snap-1589225895743525481-1-9dc86170-01c3-4570-ac05-3339c987738a.avro
[2023-04-12 18:38:02 BST] 3.7KiB STANDARD snap-4791484976322437529-1-250f2238-99fe-4d13-8e52-7a5a927c95b5.avro
[2023-04-12 18:38:52 BST] 3.7KiB STANDARD snap-5506819494114551625-1-43c11397-55c7-479c-bbf6-205a4b18f17a.avro
[2023-04-12 18:39:05 BST] 3.7KiB STANDARD snap-6262805942806938103-1-8b3afebb-a045-487a-b65c-8d9e8a44c5d0.avro
```

If we happen to have `avro-tools` and `jq` installed we can dig in a bit deeper into one of these snapshots

```shell
avro-tools tojson <(docker-compose exec -it  mc mc cat minio/warehouse/nyc/taxis/metadata/snap-6262805942806938103-1-8b3afebb-a045-487a-b65c-8d9e8a44c5d0.avro) | jq
23/04/12 18:42:48 WARN util.NativeCodeLoader: Unable to load native-hadoop library for your platform... using builtin-java classes where applicable
{
  "manifest_path": "s3://warehouse/nyc/taxis/metadata/8b3afebb-a045-487a-b65c-8d9e8a44c5d0-m1.avro",
  "manifest_length": 7411,
  "partition_spec_id": 0,
  "added_snapshot_id": {
    "long": 6262805942806938000
  },
  "added_data_files_count": {
    "int": 1
  },
  "existing_data_files_count": {
    "int": 0
  },
  "deleted_data_files_count": {
    "int": 0
  },
  "partitions": {
    "array": []
  },
  "added_rows_count": {
    "long": 17703
  },
  "existing_rows_count": {
    "long": 0
  },
  "deleted_rows_count": {
    "long": 0
  }
}
{
  "manifest_path": "s3://warehouse/nyc/taxis/metadata/8b3afebb-a045-487a-b65c-8d9e8a44c5d0-m0.avro",
  "manifest_length": 7415,
  "partition_spec_id": 0,
  "added_snapshot_id": {
    "long": 6262805942806938000
  },
  "added_data_files_count": {
    "int": 0
  },
  "existing_data_files_count": {
    "int": 0
  },
  "deleted_data_files_count": {
    "int": 1
  },
  "partitions": {
    "array": []
  },
  "added_rows_count": {
    "long": 0
  },
  "existing_rows_count": {
    "long": 0
  },
  "deleted_rows_count": {
    "long": 49162
  }
}
```

and one of the `metadata.json` files. Let's make it the latest one to make it more interesting.

```shell
I docker-spark-iceberg main+5/-1[!?⇡2]via 🌟docker-compose exec -it  mc mc cat minio/warehouse/nyc/taxis/metadata/00010-1804bb48-de71-4bf9-98af-bbaa544e5b3a.metadata.json | jq
{
  "format-version": 1,
  "table-uuid": "eb6b3a46-2ccf-4998-bce2-66cdd69661e4",
  "location": "s3://warehouse/nyc/taxis",
  "last-updated-ms": 1681321147288,
  "last-column-id": 20,
  "schema": {
    "type": "struct",
    "schema-id": 5,
    "fields": [
      ...
      {
        "id": 19,
        "name": "airport_fee",
        "required": false,
        "type": "double"
      }
    ]
  },
  "current-schema-id": 5,
  "schemas": [
    ...
    {
      "type": "struct",
      "schema-id": 5,
      "fields": [
        ...
        {
          "id": 19,
          "name": "airport_fee",
          "required": false,
          "type": "double"
        }
      ]
    }
  ],
  "partition-spec": [
    {
      "name": "VendorID",
      "transform": "identity",
      "source-id": 1,
      "field-id": 1000
    }
  ],
  "default-spec-id": 1,
  "partition-specs": [
    {
      "spec-id": 0,
      "fields": []
    },
    {
      "spec-id": 1,
      "fields": [
        {
          "name": "VendorID",
          "transform": "identity",
          "source-id": 1,
          "field-id": 1000
        }
      ]
    }
  ],
  "last-partition-id": 1000,
  "default-sort-order-id": 0,
  "sort-orders": [
    {
      "order-id": 0,
      "fields": []
    }
  ],
  "properties": {
    "owner": "root",
    "created-at": "2023-04-12T17:37:54.052498091Z",
    "write.format.default": "parquet"
  },
  "current-snapshot-id": 4791484976322437000,
  "refs": {
    "main": {
      "snapshot-id": 4791484976322437000,
      "type": "branch"
    }
  },
  "snapshots": [
    ...
    {
      "snapshot-id": 6262805942806938000,
      "parent-snapshot-id": 1509695290243621400,
      "timestamp-ms": 1681321145203,
      "summary": {
        "operation": "overwrite",
        "spark.app.id": "local-1681320992619",
        "added-data-files": "1",
        "deleted-data-files": "1",
        "added-records": "17703",
        "deleted-records": "49162",
        "added-files-size": "299938",
        "removed-files-size": "813190",
        "changed-partition-count": "1",
        "total-records": "17703",
        "total-files-size": "299938",
        "total-data-files": "1",
        "total-delete-files": "0",
        "total-position-deletes": "0",
        "total-equality-deletes": "0"
      },
      "manifest-list": "s3://warehouse/nyc/taxis/metadata/snap-6262805942806938103-1-8b3afebb-a045-487a-b65c-8d9e8a44c5d0.avro",
      "schema-id": 5
    }
  ],
  "statistics": [],
  "snapshot-log": [
    {
      "timestamp-ms": 1681321082760,
      "snapshot-id": 4791484976322437000
    },
    ...
  ],
  "metadata-log": [
    {
      "timestamp-ms": 1681321082760,
      "metadata-file": "s3://warehouse/nyc/taxis/metadata/00000-baefca3c-3770-41c8-a4d7-d459d585c7c4.metadata.json"
    },
   ...
  ]
}
```

I've abridged the verbose parts, so feel free to run this yourself if you're interested.

Let's look

## Scalable Production

Iceberg documents a potential production setup using [AWS](https://github.com/apache/iceberg/blob/master/docs/aws.md)

## Draft of a deployment design

## Working examples

## Reference

* [Apache Iceberg Spec](https://iceberg.apache.org/spec/)
* [Lakehouse Architecture with Iceberg and MinIO (by MinIO)](https://blog.min.io/lakehouse-architecture-iceberg-minio/)
* [AWS Glue native Iceberg interface documentation](https://docs.aws.amazon.com/glue/latest/dg/aws-glue-programming-etl-format-iceberg.html)
* [Hidden Partitioning Blogpost](https://www.dremio.com/blog/fewer-accidental-full-table-scans-brought-to-you-by-apache-icebergs-hidden-partitioning/)
