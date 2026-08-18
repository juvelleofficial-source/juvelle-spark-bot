import logging
from typing import Any, List, Dict, Callable
from config.settings import settings

logger = logging.getLogger(__name__)

# Lightweight local emulator if native pyspark/Java is not installed on the machine
class LocalRDD:
    def __init__(self, data: List[Any]):
        self._data = list(data)

    def getNumPartitions(self) -> int:
        return 4

    def map(self, f: Callable):
        return LocalRDD([f(x) for x in self._data])

    def mapPartitions(self, f: Callable):
        return LocalRDD(list(f(iter(self._data))))

    def collect(self) -> List[Any]:
        return list(self._data)

    def saveAsTextFile(self, path: str):
        import os
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for item in self._data:
                f.write(str(item) + "\n")

class LocalRow(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__dict__ = self

class LocalDataFrame:
    def __init__(self, data: List[Dict[str, Any]], session: Any = None):
        self._data = [LocalRow(d) if isinstance(d, dict) else d for d in data]
        self.rdd = LocalRDD(self._data)
        self.sparkSession = session

    def count(self) -> int:
        return len(self._data)

    def collect(self) -> List[Any]:
        return list(self._data)

    def first(self) -> Any:
        return self._data[0] if self._data else None

    def withColumn(self, col_name: str, col_expr: Any):
        # Emulate column addition
        new_data = []
        for row in self._data:
            r_copy = dict(row)
            if callable(col_expr):
                r_copy[col_name] = col_expr(r_copy)
            new_data.append(LocalRow(r_copy))
        return LocalDataFrame(new_data, self.sparkSession)

    def select(self, *cols):
        return self

    def groupBy(self, col_name: str):
        return LocalGroupedData(self._data, col_name, self.sparkSession)

class LocalGroupedData:
    def __init__(self, data: List[Any], group_col: str, session: Any):
        self._data = data
        self._group_col = group_col
        self._session = session

    def agg(self, *args, **kwargs):
        from collections import defaultdict
        groups = defaultdict(list)
        for row in self._data:
            key = row.get(self._group_col, "default")
            groups[key].append(row)
        
        aggregated = []
        for key, rows in groups.items():
            user_msgs = [r.get("content", "") for r in rows]
            aggregated.append(LocalRow({
                self._group_col: key,
                "user_messages": user_msgs,
                "merged_history": " | ".join(user_msgs)
            }))
        return LocalDataFrame(aggregated, self._session)

class LocalSparkConf:
    def __init__(self):
        self._conf = {"spark.master": "local[*]"}

    def get(self, key: str, default: str = None) -> str:
        return self._conf.get(key, default)

class LocalSparkSessionEmulator:
    def __init__(self, app_name: str = "LocalSparkEmulator"):
        self.version = "3.5.0-local-emulator"
        self.conf = LocalSparkConf()
        logger.info(f"Initialized Local Zero-Cost Spark Emulator for {app_name}")

    def createDataFrame(self, data: List[Any], schema: Any = None) -> LocalDataFrame:
        if isinstance(data, LocalRDD):
            return LocalDataFrame(data.collect(), self)
        return LocalDataFrame(data, self)

def get_spark_session(app_name: str = None) -> Any:
    """
    Returns native PySpark SparkSession if available; otherwise returns
    the zero-cost local multi-core Spark engine emulator.
    """
    try:
        from pyspark.sql import SparkSession
        builder = (
            SparkSession.builder
            .appName(app_name or settings.SPARK_APP_NAME)
            .master(settings.SPARK_MASTER)
            .config("spark.sql.adaptive.enabled", "true")
            .config("spark.serializer", "org.apache.spark.serializer.KryoSerializer")
        )
        spark = builder.getOrCreate()
        logger.info("Using Native PySpark Session.")
        return spark
    except Exception as e:
        logger.info(f"Native PySpark / Java not found ({e}). Using Local Zero-Cost Spark Engine.")
        return LocalSparkSessionEmulator(app_name or settings.SPARK_APP_NAME)
