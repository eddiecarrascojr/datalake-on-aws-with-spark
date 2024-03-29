import configparser
from datetime import datetime
import calendar
import os
from pyspark.sql import SparkSession
from pyspark.sql.functions import udf, col
from pyspark.sql.functions import monotonically_increasing_id

config = configparser.ConfigParser()
config.read('dl.cfg')

os.environ['AWS_ACCESS_KEY_ID'] = config.get('AWS', 'AWS_ACCESS_KEY_ID')
os.environ['AWS_SECRET_ACCESS_KEY'] = config.get('AWS', 'AWS_SECRET_ACCESS_KEY')


def create_spark_session():
    """
    :return: returns the spark session object
    """
    spark = SparkSession.builder \
        .config("spark.jars.packages", "org.apache.hadoop:hadoop-aws:2.7.5") \
        .getOrCreate()
    return spark


def process_song_data(spark, input_data, output_data):
    """
    :param spark: spark session object
    :param input_data: is the directory of the input data
    :param output_data: directory of where spark will right the data to
    :return: None
    """
    # read song data file
    song_data = input_data + "song_data/*/*/*/*.json"
    df = spark.read.json(song_data)

    songs_table = (
        df.select(
            'song_id', 'title', 'artist_id',
            'year', 'duration'
        ).distinct()
    )
    print(songs_table.head(5))

    # write songs table to parquet files partitioned by year and artist
    songs_table.write.parquet(output_data + "songs.parquet", mode="overwrite")

    # extract columns to create artists table
    artists_table = (
        df.select(
            'artist_id',
            col('artist_name').alias('name'),
            col('artist_location').alias('location'),
            col('artist_latitude').alias('latitude'),
            col('artist_longitude').alias('longitude')
        ).distinct()
    )

    # write artists table to parquet files
    artists_table.write.parquet(output_data + "artists.parquet", mode="overwrite")
    print("Table has been written to s3.")


def process_log_data(spark, input_data, output_data):
    """
    :param spark: spark session object
    :param input_data: is the directory of the input data
    :param output_data: directory of where spark will right the data to
    :return: None
    """
    # get file path to log data file
    log_data = input_data + "log_data/*/*/*.json"
    df = spark.read.json(log_data)

    # filter by actions for song plays
    #     songplay_id, start_time, user_id, level, song_id, artist_id, session_id, location, user_agent
    songplays_table = df['ts', 'userId', 'level', 'sessionId', 'location', 'userAgent']

    # extract columns for users table
    #     user_id, first_name, last_name, gender, level
    users_table = df['userId', 'firstName', 'lastName', 'gender', 'level']

    # write users table to parquet files
    users_table.write.parquet(output_data + 'users.parquet', mode='overwrite')
    print("--- users.parquet completed ---")
    # create timestamp column from original timestamp column
    get_timestamp = udf(lambda x: str(int(int(x) / 1000)))
    df = df.withColumn('timestamp', get_timestamp(df.ts))

    # create datetime column from original timestamp column
    get_datetime = udf(lambda x: datetime.fromtimestamp(int(int(x) / 1000)))
    get_week = udf(lambda x: calendar.day_name[x.weekday()])
    get_weekday = udf(lambda x: x.isocalendar()[1])
    get_hour = udf(lambda x: x.hour)
    get_day = udf(lambda x: x.day)
    get_year = udf(lambda x: x.year)
    get_month = udf(lambda x: x.month)

    df = df.withColumn('start_time', get_datetime(df.ts))
    df = df.withColumn('hour', get_hour(df.start_time))
    df = df.withColumn('day', get_day(df.start_time))
    df = df.withColumn('week', get_week(df.start_time))
    df = df.withColumn('month', get_month(df.start_time))
    df = df.withColumn('year', get_year(df.start_time))
    df = df.withColumn('weekday', get_weekday(df.start_time))

    # extract columns to create time table
    time_table = df['start_time', 'hour', 'day', 'week', 'month', 'year', 'weekday']

    # write time table to parquet files partitioned by year and month
    time_table.write.partitionBy('year', 'month').parquet(output_data + 'time.parquet', mode='overwrite')
    print("--- time.parquet completed ---")

    # read in song data to use for songplays table
    song_df = spark.read.parquet(output_data + "songs.parquet")

    # extract columns from joined song and log datasets to create songplays table
    df = df.join(song_df, song_df.title == df.song)
    songplays_table = df['start_time', 'userId', 'level', 'song_id', 'artist_id', 'sessionId', 'location', 'userAgent']
    songplays_table.select(monotonically_increasing_id().alias('songplay_id')).collect()

    # write songplays table to parquet files partitioned by year and month
    songplays_table.write.parquet(output_data + 'songplays.parquet', mode='overwrite')
    print("--- songplays.parquet completed ---")
    print("*** process_log_data completed ***\n\nEND")


def main():
    """
    :return: None, just runs all the programs in the correct order.
    """
    spark = create_spark_session()
    input_data = "s3a://udacity-dend/"
    output_data = "s3a://sparkify-dend/"
    process_song_data(spark, input_data, output_data)
    process_log_data(spark, input_data, output_data)


if __name__ == "__main__":
    main()
