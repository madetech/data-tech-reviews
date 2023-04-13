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
* [Comparison with other data lake filesystems](#comparison-with-other-data-lake-filesystems)
    * [Iceberg vs Delta](#iceberg-vs-delta)
        * [Maturity](#maturity)
        * [Unique to Iceberg](#unique-to-iceberg)
            * [Concurrent Writes to Same Table](#concurrent-writes-to-same-table)
            * [Partition Layout Evolution](#partition-layout-evolution)
        * [Common to Both](#common-to-both)
            * [ACID transactions](#acid-transactions)
        * [Time Travel](#time-travel)
        * [Version Rollback](#version-rollback)
        * [Unique to Delta](#unique-to-delta)
    * [Iceberg vs Apache Hive](#iceberg-vs-apache-hive)
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

### Iceberg Table Specification

Iceberg was designed to run completely abstracted from physical storage using object storage. All locations are “explicit, immutable, and absolute” as defined in metadata

They make a point of saying that the intended use case is for a large, but slow-changing dataset.

>...large, slow-changing collection of files built on open formats over a distributed filesystem or key-value store

The envisioned architecture is detailed in the follow graphic ![Graphic detailing target architecture of Iceberg.](https://iceberg.apache.org/img/iceberg-metadata.png)

This graphic describes a single stateful service (Catalog) operating in (presumably) API layer, which operates on the file store directly in the metadata/data layers.

Digging into this we can see that the state of the service is simply to hold a pointer to the latest table state in the form of a metadata file (swapped atomically)

### Catalog Service

Iceberg supports a variety of Catalog implementations, the following have in-tree Java Service and pyiceberg client implementations:

* Iceberg's native REST Catalog
* JDBC Catalog
* Hive Catalog
* Spark Catalog
* AWS Glue Catalog

Additionally, pyiceberg includes support for working with out-of-tree catalog implementations:

* DynamoDb Catalog

## Integrations

### Spark

Iceberg uses a subset of spark isolation levels, namely `seriaizable`

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

#### Time Travel
    <!-- Time travel enables reproducible queries that use exactly the same table snapshot, or lets users easily examine changes -->

#### Version Rollback
    <!-- Version rollback allows users to quickly correct problems by resetting tables to a good state -->

#### Unique to Delta

### Iceberg vs Apache Hive


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
[root@644ea375ae1e /]# mc ls minio/warehouse/nyc/taxis/metadata
[2023-04-05 11:22:31 UTC] 5.7KiB STANDARD 00000-ce92d882-3a0c-4da9-9381-47e7202b30d2.metadata.json
[2023-04-05 13:34:24 UTC] 8.0KiB STANDARD 00001-2bf25b14-a1f3-4382-b70c-f02b457331d2.metadata.json
[2023-04-05 13:34:25 UTC]  10KiB STANDARD 00002-3a0ff43d-a594-48b6-b9bd-c9d4c0fb7700.metadata.json
[2023-04-05 13:34:33 UTC]  12KiB STANDARD 00003-657706b3-2242-41ef-9fe6-e895d9008dbd.metadata.json
[2023-04-05 13:34:39 UTC]  15KiB STANDARD 00004-3e287c98-db3a-4379-ad7e-458e6a82b3fe.metadata.json
[2023-04-05 13:34:41 UTC]  17KiB STANDARD 00005-d2a4d7fd-1baa-4383-9f1f-e2d1bdcaa973.metadata.json
[2023-04-05 13:35:34 UTC]  18KiB STANDARD 00006-7e343547-95fc-4fca-86bd-8786fc905c6e.metadata.json
[2023-04-05 14:48:16 UTC]  20KiB STANDARD 00007-88817038-9c57-4d97-b68e-e84adefc8784.metadata.json
[2023-04-05 14:48:18 UTC]  20KiB STANDARD 00008-6c38668e-453c-445c-b784-91d9300f6b63.metadata.json
[2023-04-05 11:22:30 UTC] 7.1KiB STANDARD 0f1ea0a5-042d-4ac1-8b19-1854a5a5c529-m0.avro
[2023-04-05 13:35:34 UTC] 7.3KiB STANDARD 43806d73-bcc5-47a0-bb6d-7013f4f74632-m0.avro
[2023-04-05 13:35:34 UTC] 7.3KiB STANDARD 43806d73-bcc5-47a0-bb6d-7013f4f74632-m1.avro
[2023-04-05 14:48:16 UTC] 7.3KiB STANDARD c3aa91ce-d7d8-4fcb-aaab-d88ed8731b0b-m0.avro
[2023-04-05 14:48:16 UTC] 7.2KiB STANDARD c3aa91ce-d7d8-4fcb-aaab-d88ed8731b0b-m1.avro
[2023-04-05 14:48:18 UTC] 7.2KiB STANDARD e988964c-d659-4f95-a822-3470aa4b9eb0-m0.avro
[2023-04-05 14:48:18 UTC] 7.2KiB STANDARD e988964c-d659-4f95-a822-3470aa4b9eb0-m1.avro
[2023-04-05 14:48:16 UTC] 3.7KiB STANDARD snap-2297595345938034492-1-c3aa91ce-d7d8-4fcb-aaab-d88ed8731b0b.avro
[2023-04-05 13:35:34 UTC] 3.7KiB STANDARD snap-2915614949473073220-1-43806d73-bcc5-47a0-bb6d-7013f4f74632.avro
[2023-04-05 11:22:30 UTC] 3.7KiB STANDARD snap-4233008376301842836-1-0f1ea0a5-042d-4ac1-8b19-1854a5a5c529.avro
[2023-04-05 14:48:18 UTC] 3.7KiB STANDARD snap-6535515243957684082-1-e988964c-d659-4f95-a822-3470aa4b9eb0.avro
```

## Scalable Production

## Draft of a deployment design

## Working examples

## Reference

* [Apache Iceberg Spec](https://iceberg.apache.org/spec/)
* [Lakehouse Architecture with Iceberg and MinIO (by MinIO)](https://blog.min.io/lakehouse-architecture-iceberg-minio/)
* [AWS Glue native Iceberg interface documentation](https://docs.aws.amazon.com/glue/latest/dg/aws-glue-programming-etl-format-iceberg.html)
* [Hidden Partitioning Blogpost](https://www.dremio.com/blog/fewer-accidental-full-table-scans-brought-to-you-by-apache-icebergs-hidden-partitioning/)
