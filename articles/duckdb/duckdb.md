![DuckDB logo](ducklogo.png)

### Overview

DuckDB has emerged as a powerful, open-source SQL OLAP database management system. MT have effectively utilized DuckDB as a data processing tool in our ongoing Internal Forecasting project. The project follows a raw-to-gold medallion architecture on GCP, with DuckDB providing a viable alternative to established tools like Polars and Python Pandas. This review will provide a concise analysis of DuckDB, discussing its core components, limitations and licensing details, while comparing it with its competitors in the context of Made Tech's use case.

### A Comparison with Polars

Polars, an open-source DataFrame library implemented in Rust, has been gaining traction as a high-performance data manipulation tool. While both DuckDB and Polars focus on efficient data processing, there are some key differences to consider.

First, DuckDB is a full-fledged SQL database system, whereas Polars is primarily a DataFrame library. DuckDB supports standard SQL query language, making it more accessible to those with prior SQL experience. Polars, on the other hand, uses its own syntax and function names, which can be a learning curve for some users.

Second, DuckDB shines in its ability to handle large datasets, often outperforming Polars in terms of performance. It achieves this through vectorized query execution, parallel processing, and advanced compression techniques. Polars, while fast, may not always match DuckDB's performance for massive data.

In a short test comparing the time to perform a basic aggregation between the two, DuckDB demonstrated a marginal advantage over Polars, see [performance.py](performance.py).

```
DuckDB avg time: 0.003796 seconds

Polars avg time: 0.004082 seconds
```


### A Comparison with Python Pandas

Python Pandas, a popular DataFrame library, has long been the preferred tool in data science for data manipulation and analysis. Nevertheless, DuckDB offers several benefits that warrant a closer examination.

DuckDB's most significant edge over Pandas is its performance. Its vectorized query execution and other optimizations allow it to process large datasets much faster than Pandas. Additionally, DuckDB's native support for SQL queries makes it a more natural fit for those accustomed to SQL-based data manipulation.

Furthermore, DuckDB's integration with Pandas allows users to run SQL queries directly on Pandas DataFrames, leveraging the strengths of both tools. This symbiosis provides users with the best of both worlds, combining Pandas' versatility with DuckDB's performance.

### Main Components

DuckDB's architecture consists of three main components: storage, execution, and optimizer. The storage component deals with data organization and compression, optimizing how data is stored to enable efficient querying. The execution component utilizes a vectorized query engine, allowing for high-performance parallel processing of data. Lastly, the optimizer is responsible for transforming SQL queries into efficient execution plans, ensuring that the system operates at peak performance.

### Limitations

Although DuckDB is an impressive solution, it has some limitations. Firstly, it is an OLAP-focused system, meaning it is optimized for analytical queries and not designed for transaction-heavy workloads (OLTP). Organizations with high transactional requirements may need to look elsewhere.

Secondly, DuckDB lacks the ecosystem and community support that more established solutions like Python Pandas have. While this may change over time, users may encounter fewer resources and support options as they work with DuckDB.

Lastly, as DuckDB is still a relatively young project, some users may experience bugs and issues that are yet to be ironed out. These growing pains are typical of emerging technologies, and users should be prepared to encounter some hiccups.

## Licensing and Pricing

DuckDB is an open-source project, meaning it is free to use and modify. It is licensed under the permissive MIT License, which allows for commercial use, distribution, modification, and sublicensing without imposing significant restrictions. 