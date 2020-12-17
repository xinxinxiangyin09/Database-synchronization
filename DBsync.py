"""
    数据库同步脚本
"""

import os
import sys
import pymysql
import yaml
import datetime
import time
import json
from pymongo import MongoClient

# json格式化输出
class DateEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.strftime("%Y-%m-%d %H:%M:%S")
        else:
            return json.JSONEncoder.default(self, obj)

def diyPrint(grade, info):
    """
    日志输出
    :param grade: 日志等级，0为信息，1为报错
    :param info: 日志信息
    :return:
    """
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if grade == 0:
        grade = "info"
        print("\033[32m[%s] %s %s\033[0m" % (now, grade, info))
    elif grade == 1:
        grade = "error"
        print("\033[31m[%s] %s %s\033[0m" % (now, grade, info))


class Spider(object):
    def __init__(self):
        # 加载配置文件，获取mongoDB的连接信息
        try:
            self.yamlPath = os.path.join(os.path.dirname(__file__), "config.yaml")
            with open(self.yamlPath, "r", encoding="utf-8") as f:
                content = f.read()
            self.config = yaml.load(content, Loader=yaml.FullLoader)
            diyPrint(0, "配置文件加载成功，mongo地址为：%s" % self.config["mongoDB"]["host"])
        except Exception as err:
            diyPrint(1, "配置信息读取错误，错误信息：%s" % err)

        # 连接mongoDB数据库
        try:
            host = self.config["mongoDB"]["host"]
            port = self.config["mongoDB"]["port"]
            user = self.config["mongoDB"]["user"]
            password = self.config["mongoDB"]["password"]
            self.client = MongoClient(host=host, port=port, username=user, password=password)
            self.db = self.client.ProConfig
            diyPrint(0, "MongoDB数据库连接成功")
        except Exception as err:
            diyPrint(1, "MongoDB数据库连接错误：%s" % err)

        # 读取数据库配置信息
        serverConfig = self.db.serverconfig

        # 主数据库连接
        try:
            mainConfig = serverConfig.find({"type": "main"})[0]
            self.db1 = pymysql.connect(
                host=mainConfig["host"],
                port=int(mainConfig["port"]),
                user=mainConfig["user"],
                password=mainConfig["password"],
                database=mainConfig["database"],
                charset=mainConfig["charset"]
            )
            self.cursor1 = self.db1.cursor(pymysql.cursors.DictCursor)
            diyPrint(0, "主数据库连接成功：%s:%s" % (mainConfig["host"], int(mainConfig["port"])))
        except Exception as err:
            diyPrint(1, "主数据库连接错误，错误信息：%s" % err)
            sys.exit()

        # 从数据库连接
        try:
            secConfig = serverConfig.find({"type": "sec"})[0]
            self.db2 = pymysql.connect(
                host=secConfig["host"],
                port=int(secConfig["port"]),
                user=secConfig["user"],
                password=secConfig["password"],
                database=secConfig["database"],
                charset=secConfig["charset"]
            )
            self.cursor2 = self.db2.cursor(pymysql.cursors.DictCursor)
            diyPrint(0, "从数据库连接成功：%s:%s" % (secConfig["host"], int(secConfig["port"])))
        except Exception as err:
            diyPrint(1, "从数据库连接错误，错误信息：%s" % err)
            sys.exit()

    def log(self, grade, info):
        log = self.db.log
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log.insert({"time": now, "grade": grade, "info": info})

    def lastID(self, tableName, lastId=None):
        """
        修改记录ID值，若未提供lastId，则返回当前表的endID值
        :param tableName: 表名
        :param lastId: 最后一个ID值
        :return:
        """
        hisSet = self.db.his

        # 修改lastID值
        if lastId is not None:
            try:
                hisSet.update({"tablename": tableName}, {"$set": {"value": int(lastId)}})
                diyPrint(0, "lastID更新为%s" % lastId)
            except Exception as err:
                diyPrint(1, "lastID更新失败，程序退出：%s" % err)
                sys,exit()

        # 查找lastID值
        elif lastId is None:
            try:
                lastID = hisSet.find_one({"tablename": tableName})
                return lastID["value"]
            except Exception as err:
                diyPrint(1, "lastID查询失败，程序退出：%s" % err)
                sys,exit()

    # 获取容错的数据
    def getData(self, tableName):
        while True:
            sql = "select max(id) from %s;" % tableName
            self.cursor1.execute(sql)
            oldLastID = self.cursor1.fetchall()[0]["max(id)"]
            if int(oldLastID) > int(self.lastID(tableName=tableName)):
                sql = "select * from %s where id > %s ORDER BY id ASC LIMIT 20;" %(tableName, self.lastID(tableName= tableName))
                self.cursor1.execute(sql)
                data = self.cursor1.fetchall()

                # 记录成功与失败的数量
                success = 0
                faild = 0
                for info in data:
                    result = self.save(tableName=tableName, info=info)
                    if result == "ok":
                        success += 1
                    else:
                        faild += 1

                # 更新ID记录值
                self.lastID(tableName=tableName, lastId=data[-1]["id"])

                if faild == 0:
                    self.log(0, "%s 成功推送%s条数据" % (tableName, success))
                else:
                    self.log(1, "%s 共%s条数据推送失败" % (tableName, faild))
            else:
                self.log(0, "%s 无新增数据" % tableName)
                diyPrint(0, "%s 无新增数据" % tableName)
                break

    # 容错数据的推送
    def save(self, info, tableName):
        try:
            cols = ", ".join('`{}`'.format(k) for k in info.keys())
            val_cols = ', '.join('%({})s'.format(k) for k in info.keys())
            sql = "insert into {table_name}(%s) values(%s)".format(table_name=tableName)
            res_sql = sql % (cols, val_cols)
            self.cursor2.execute(res_sql, info)
            self.db2.commit()
            diyPrint(0, "%s %s success" % (tableName, json.dumps(info, cls=DateEncoder, ensure_ascii=False)))
            return "ok"
        except Exception as err:
            diyPrint(1, info="%s %s %s error" % (tableName, info, err))

    def main(self):
        while True:
            for tableName in self.db.his.find():
                tableName = tableName["tablename"]
                self.getData(tableName)
            diyPrint(0, "同步完成，休眠%s秒" % self.config["sleep"])
            time.sleep(self.config["sleep"])

    def __del__(self):
        try:
            self.cursor1.close()
            self.db1.close()
        except Exception as err:
            diyPrint(1, "主数据库断开错误，请手动回收连接释放内存：%s" % err)
        try:
            self.cursor2.close()
            self.db2.close()
        except Exception as err:
            diyPrint(1, "从数据库断开错误，请手动回收连接释放内存：%s" % err)
        try:
            self.client.close()
        except Exception as err:
            diyPrint(1, "mongo数据库断开错误，请手动回收连接释放内存：%s" % err)


if __name__ == '__main__':
    try:
        spider = Spider()
        spider.main()
    except KeyboardInterrupt:
        diyPrint(1, "用户自行退出")
