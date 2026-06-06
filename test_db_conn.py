import psycopg2


def test_connection():
    try:
        # 替换为你自己的数据库信息
        connection = psycopg2.connect(
            user="postgres",  # 默认用户名
            password="your_password",  # 你的数据库密码
            host="127.0.0.1",  # 服务器IP地址
            port="5432",  # 默认端口
            database="postgres"  # 默认连接的数据库名
        )

        cursor = connection.cursor()

        # 执行一个简单的 SQL 查询：打印数据库版本
        cursor.execute("SELECT version();")
        db_version = cursor.fetchone()

        print("连接成功！")
        print(f"PostgreSQL 版本: {db_version}")

        # 关闭连接
        cursor.close()
        connection.close()

    except Exception as error:
        print(f"连接失败: {error}")


if __name__ == "__main__":
    test_connection()
