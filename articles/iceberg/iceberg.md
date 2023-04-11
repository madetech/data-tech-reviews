# Apache Iceberg

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

#### Open Format Specification

Version 1 and 2 of the format specification have been completed and adopted by the community. The two releases see to be additive in scope.

### Java Libraries

Apache Iceberg v1.0 was released in November 2022.

### Pyiceberg

Pyiceberg is versioned separately despite being part of the Iceberg git repository, and is yet to have a major release (version 0.13 at time of writing).

## What Are the Goals of Iceberg?

#### Serializable isolation

> Reads will be isolated from concurrent writes and always use a committed snapshot of a table’s data. Writes will support removing and adding files in a single operation and are never partially visible. Readers will not acquire locks.

Essentially what this means is that Iceberg has two Isolation Levels for two seperate use cases, notions of transactionality Essentially

> Speed – Operations will use O(1) remote calls to plan the files for a scan and not O(n) where n grows with the size of the table, like the number of partitions or files.
> Scale – Job planning will be handled primarily by clients and not bottleneck on a central metadata store. Metadata will include information needed for cost-based optimization.
> Evolution – Tables will support full schema and partition spec evolution. Schema evolution supports safe column add, drop, reorder and rename, including in nested structures.
> Dependable types – Tables will provide well-defined and dependable support for a core set of types.
> Storage separation – Partitioning will be table configuration. Reads will be planned using predicates on data values, not partition values. Tables will support evolving partition schemes.
> Formats – Underlying data file formats will support identical schema evolution rules and types. Both read-optimized and write-optimized formats will be available.

<!-- ### Format Specification -->

#### Schema evolution
    supports add, drop, update, or rename, and has no side-effects

#### Hidden Paritioning
    Hidden partitioning prevents user mistakes that cause silently incorrect results or extremely slow queries

#### Parition Layout Evolution
    Partition layout evolution can update the layout of a table as data volume or query patterns change

#### Time Travel
    Time travel enables reproducible queries that use exactly the same table snapshot, or lets users easily examine changes

#### Version Rollback
    Version rollback allows users to quickly correct problems by resetting tables to a good state

<!-- ### Catalog -->

### ACID transactions

ACID transactionality seems to be provided via the Catalog implementation. How exactly this works for the use case of direct comm Apache Hive (which is provided via built in to Iceberg)

### pyiceberg

## Main components

### Iceberg Table Specification

In contrast, Iceberg was designed to run completely abstracted from physical storage using object storage. All locations are “explicit, immutable, and absolute” as defined in metadata

* operating on top of a distributed file system with data stored in one of several open file formats (Avro, Parquet, and ORC) and metadata (Avro)

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

## Comparison with other data lake filesystems

### Iceberg vs Delta

Iceberg not at t

Iceberg does have several features' delta is lacking. Iceberg supports concurrent writes to the same Delta table from multiple spark drivers natively, whereas Delta requires a [workaround using DynamoDB and explicit feature/version toggle on all LogStore writers](https://docs.delta.io/latest/delta-storage.html#-delta-storage-s3-multi-cluster)

## Starting simple

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

## Core concepts

###

## Reference

* [Lakehouse Architecture with Iceberg and MinIO (by MinIO)](https://blog.min.io/lakehouse-architecture-iceberg-minio/)
* [AWS Glue native Iceberg interface documentation](https://docs.aws.amazon.com/glue/latest/dg/aws-glue-programming-etl-format-iceberg.html)
