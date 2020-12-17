"""
    项目初始化
"""

import yaml
import os
import pymongo
import datetime
import sys
import pymysql

################## 程序配置 ##################
serverConfig = [
    # 主服务器
    {"host": "", "port": 3306, "user": "", "password": "", "database": "", "charset": "utf8mb4"},
    # 从服务器
    {"host": "", "port": 3306, "user": "", "password": "", "database": "", "charset": "utf8mb4"}
]

# 需要同步的表
tableNames = [
    'user_number',
    'user_info',
    'user_umps',
    'tech_data'
]

################## 程序主体 ##################
def myPrint(grade, info):
    """个性化打印台"""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if grade == 0:
        print("\033[32m[%s] info %s\033[0m" %(now, info))
    elif grade == 1:
        print("\033[31m[%s] error %s\033[0m" % (now, info))

class Init(object):
    def __init__(self):
        try:
            configPath = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
            configPath = os.path.join(configPath, "config.yaml")
            with open(configPath, "r", encoding="utf-8") as f:
                content = f.read()
            config = yaml.load(content, Loader=yaml.FullLoader)["mongoDB"]
            myPrint(0, "配置文件加载成功")
        except Exception as err:
            myPrint(1, "配置文件加载失败：%s" % err)
            sys.exit()

        try:
            self.client = pymongo.MongoClient(
                host=config["host"],
                port=int(config["port"]),
                username=config["user"],
                password=config["password"],
            )
            self.db = self.client.ProConfigTest
            myPrint(0, "mongo数据库连接成功")
        except Exception as err:
            myPrint(1, "mongo数据库连接失败：%s" % err)
            sys.exit()

    def serverConfig(self):
        """创建数据库配置"""
        try:
            cursor = self.db.serverConfig
            cursor.remove()
            cursor.insert(
                [
                    {"_id": 1, "type": "main", "host": serverConfig[0]["host"], "port": serverConfig[0]["port"], "user": serverConfig[0]["user"],
                     "password": serverConfig[0]["password"], "database": serverConfig[0]["database"], "charset": serverConfig[0]["charset"]},
                    {"_id": 2, "type": "sec", "host": serverConfig[1]["host"], "port": serverConfig[1]["port"], "user": serverConfig[1]["user"],
                     "password": serverConfig[1]["password"], "database": serverConfig[1]["database"], "charset": serverConfig[1]["charset"]}
                ]
            )
            myPrint(0, "主从数据库配置添加成功")
        except Exception as err:
            myPrint(1, "主从数据库配置添加失败：" % err)

    def his(self):
        """创建his表，记录ID值"""
        try:
            cursor = self.db.his
            cursor.remove()
            insert_info = []
            for table in tableNames:
                insert_info.append({"_id": tableNames.index(table) + 1, "tablename": table, "value": 0})

            cursor.insert(insert_info)
            myPrint(0, "表映射关系创建成功")
        except Exception as err:
            myPrint(1, "表映射关系创建失败:%s" % err)

    def structure(self, tableName):
        """同步表结构"""
        try:
            # 主数据库
            config = self.db.serverConfig.find()
            dbOne = pymysql.connect(
                host=config[0]["host"],
                port=config[0]["port"],
                user=config[0]["user"],
                password=config[0]["password"],
                database=config[0]["database"],
                charset=config[0]["charset"]
            )
            dbTwo = pymysql.connect(
                host=config[1]["host"],
                port=config[1]["port"],
                user=config[1]["user"],
                password=config[1]["password"],
                database=config[1]["database"],
                charset=config[1]["charset"]
            )
            cursorOne = dbOne.cursor(pymysql.cursors.DictCursor)
            cursorTwo = dbTwo.cursor(pymysql.cursors.DictCursor)

            # 清空从数据库的表
            try:
                sql = "drop table %s;" % tableName
                cursorTwo.execute(sql)
                dbTwo.commit()
            except Exception:
                pass

            # 同步表结构
            sql = "show create table %s;" % tableName
            cursorOne.execute(sql)
            create_sql = cursorOne.fetchall()[0]["Create Table"]
            cursorTwo.execute(create_sql)
            dbTwo.commit()
            myPrint(0, "【%s】表结构同步成功" % tableName)

            cursorOne.close()
            cursorTwo.close()
        except Exception as err:
            myPrint(1, "【%s】表结构同步失败：%s" % (tableName, err))
            sys.exit()

    def main(self):
        self.serverConfig()
        self.his()
        for tableName in tableNames:
            self.structure(tableName=tableName)
        myPrint(0, "恭喜您，环境初始化成功！")

    def __del__(self):
        try:
            self.client.close()
            myPrint(0, "mongo已断开连接")
        except Exception as err:
            myPrint(1, "mongo断开失败，请手动回收：%s" % err)


################## 程序入口 ##################
if __name__ == '__main__':
    Init().main()
