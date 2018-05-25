from slackbot.bot import Bot
from slackbot.bot import respond_to
import pymysql
import configparser
import pyHyperV
import random
import string
import pymssql
from datetime import datetime, timedelta
from rmbsnipeit import Assets, Users

# подгружаем конфиг
# slackbot_settings.py - Slack BOT API Token
config = configparser.ConfigParser()
config.read("config.ini")

# admin list
admin_list = config["admin"]["admin_list"]

# sco config data
sco_host = config["sco"]["host"]
# sco_username = config["sco"]["username"]
# sco_password = config["sco"]["password"]


def main():
    bot = Bot()
    bot.run()


class database(object):
    def __init__(self):
        self.db_host = config["db"]["host"]
        self.db_port = '3306'
        self.db_user = config["db"]["user"]
        self.db_pass = config["db"]["passwd"]
        self.db_name = config["db"]["db"]
        # create connection
        self.db_connect = pymysql.connect(host=self.db_host,
                                          user=self.db_user,
                                          passwd=self.db_pass,
                                          db=self.db_name,
                                          charset='utf8'
                                          )
        # create cursor
        self.cursor = self.db_connect.cursor(pymysql.cursors.DictCursor)

    def execute(self, sql: object, something: object) -> object:
        self.something = something
        self.cursor.execute(sql, something)
        self.sql_result = self.cursor.fetchall()

    def close(self):
        self.cursor.close()
        self.db_connect.close()


# custom messages
text_messages = {
    'help_commands':
        '*Инвентаризация:*\n'
        '- *device nb123rds* или *device nb123%*\n'
        '- *user a.ivanov* или *user иванов* или *user %ivanov%*\n'
        '- *store nb*/*dt*/*mac*/*mb*/*mn*\n    где nb - notebook, dt - desktop, mac - apple, mb - monoblock(all-in-one), mn - monitor\n\n\n'
        '*Команды:*\n'
        '*printer* - текущий статус принтеров\n'
        '*adrep* - репликация Active Directory (в чате - @iprobot adrep, в привате - adrep)\n'
        '*pwd* - генератор паролей для пользователей, можно указать длину пароля - *pwd 50*\n\n'
        '*SnipeIT*:\n'
        '*checkin mn113, mn112* - списать на склад\n'
        '*checkout user.name mn113, mn112* - выдать на пользователя user.name список девайсов\n',

    'if_not_admin':
        'You do not have rights to get information from this bot. Please, contact with @masyan'

}

@respond_to('servers')
def servers_updates(message):
    # SCCM connection
    sccm_server = config["sccm"]["server"]
    sccm_user = config["sccm"]["user"]
    sccm_password = config["sccm"]["password"]

    conn = pymssql.connect(sccm_server, sccm_user, sccm_password, 'CM_RMB')
    cursor = conn.cursor(as_dict=True)
    sql = ("""
    select  distinct 

    os.Netbios_Name0,
    ucs.LocalizedDisplayName,
    -- ucs.LocalizedInformativeURL,
    -- ucs.MachineID,
    -- ucs.Status,
    -- ucs.CI_ID,
    -- ucs.LastEnforcementMessageID,

    CASE 
    when ucs.LastEnforcementMessageID =  '1' then 'Enforcement started'
    when ucs.LastEnforcementMessageID =  '3' then 'Waiting for another installation'
    when ucs.LastEnforcementMessageID =  '6' then 'General failure'
    when ucs.LastEnforcementMessageID =  '8' then 'Installing updates'
    when ucs.LastEnforcementMessageID =  '9' then 'Pending Restart'
    when ucs.LastEnforcementMessageID =  '10' then 'Successfully Installed'
    when ucs.LastEnforcementMessageID =  '11' then 'Failed to install'
    when ucs.LastEnforcementMessageID =  '12' then 'Downloading updates'
    when ucs.LastEnforcementMessageID =  '13' then 'Downloaded updates'

            end as ClientID

    from fn_ListUpdateComplianceStatus(1033) AS ucs 
    INNER JOIN 
            (vSMS_UpdatesAssignment AS ua 
            LEFT OUTER JOIN vCI_AssignmentTargetedCIs AS uavCI_AssignmentTargetedCIs ON ua.AssignmentID = uavCI_AssignmentTargetedCIs.AssignmentID ) 
                                                ON ucs.CI_ID = uavCI_AssignmentTargetedCIs.CI_ID   
    INNER join v_R_System as OS on ucs.MachineID = os.ResourceID
    where ucs.MachineID in (select resourceid from v_r_system where operatingSystem0 like '%Server%')
    -- ('16781178', '16781199', '16781284'))



    """)
    cursor.execute(sql)
    row = cursor.fetchall()

    result = []

    if len(row) != 0:
        from collections import Counter
        from itertools import groupby

        # netbios_name = lambda x: x['Netbios_Name0']
        main_server_status = {k: Counter(d['ClientID'] for d in g) for k, g in
                              groupby(row, (lambda x: x['Netbios_Name0']))}
        for i, k in main_server_status.items():
            # print(i, k.values())
            updates_status = ['- {} (*{}*)'.format(ks, vs) for ks, vs in k.items()]
            message.reply('*{}*\t{}'.format(i.lower(), ' '.join(updates_status)).expandtabs(12))

    conn.close()


@respond_to('help')
def commands_list(message):
        # take username from reply
    username = "{}".format(message._client.users.get(message.body["user"])["name"])

    # check admin permissions
    if username in admin_list:
        message.reply(text_messages['help_commands'])

    else:
        message.reply(text_messages['if_not_admin'])


@respond_to('(checkin) (.*\,.*|.*)')
def checkin_assets(message, check, devices):
    username = "{}".format(message._client.users.get(message.body["user"])["name"])
    if username in admin_list:
        for device in devices.split(', '):
            deviceID = Assets().getID(config["snipeit"]["server"], config["snipeit"]["token"], device.upper())
            # print('DeviceID: ' + str(deviceID))
            payload = {
                    "id": deviceID
                }
            checkin_message = Assets().checkin(config["snipeit"]["server"], config["snipeit"]["token"], str(deviceID),
                                                   payload)
            message.reply('*{0}* - {1}'.format(device.upper(), checkin_message))
    else:
        message.reply(text_messages['if_not_admin'])


@respond_to('(checkout) ([^\s]+) (.*\,.*|.*)')
def assets(message, check, adusername, devices):
    username = "{}".format(message._client.users.get(message.body["user"])["name"])
    if username in admin_list:
        for device in devices.split(', '):
            deviceID = Assets().getID(config["snipeit"]["server"], config["snipeit"]["token"], device.upper())
            # print('DeviceID: ' + str(deviceID))
            r = Users().getID(config["snipeit"]["server"], config["snipeit"]["token"], adusername)
                # print('UserID: ' + str(r))
            payload = {
                    "id": deviceID,
                    "user_id": r,
                    "assigned_user": r,
                    "checkout_to_type": "user"

                }
            checkout_message = Assets().checkout(config["snipeit"]["server"], config["snipeit"]["token"], str(deviceID), payload)
            # print(checkout_message)

            message.reply('*{0}* - {1} - {2}'.format(device.upper(), adusername, checkout_message))
    else:
        message.reply(text_messages['if_not_admin'])


@respond_to('adrep')
def commands_list(message):
        # take username from reply
    username = "{}".format(message._client.users.get(message.body["user"])["name"])

    # check admin permissions
    if username in admin_list:
        message.reply('Active Directory replication is starting by {}'.format(username))
        
        o = pyHyperV.orchestrator(sco_host, sco_username, sco_password)

        runbookID = '4220d0bb-9be8-4130-8a86-40d3029d77c3'
        runbookParameters = {
            '8eb7081d-e53e-4b1a-9c1e-c2bcd0e09df7': username
        }

        o.Execute(runbookID, runbookParameters)

    else:
        message.reply(text_messages['if_not_admin'])


def get_random_password(size=4):
    a1 = ''.join(random.choice('BCDFGHKLMNPRSTVWXZ'))
    a2 = ''.join(random.choice('aeouy'))
    a3 = ''.join(random.choice('bcdfghkmnprstvwxz'))
    a4 = ''.join(random.choice('aeouy'))
    digits = ''.join(random.choice('123456789') for _ in range(size))
    return a1+a2+a3+a4+digits


@respond_to('pwd$')
def send_pwd(message):
    message.reply(get_random_password())


def get_complex_password(size=25, chars=string.ascii_uppercase + string.digits + string.ascii_lowercase):
    return ''.join(random.choice(chars) for _ in range(size))


@respond_to('pwd (\d*)')
def send_pwd(message, something):
    if something:
        message.reply(get_complex_password(int(something)))
    else:
        pass


@respond_to('printer$')
def printers(message):
        # take username from reply
    username = "{}".format(message._client.users.get(message.body["user"])["name"])

    # check admin permissions
    if username in admin_list:

        # SCOM connection
        scom_server = config["scom"]["server"]
        scom_user = config["scom"]["user"]
        scom_password = config["scom"]["password"]

        conn = pymssql.connect(scom_server, scom_user, scom_password, 'OperationsManager')
        cursor = conn.cursor(as_dict=True)
        cursor.execute(
            "select MonitoringObjectDisplayName, MonitoringObjectName, TimeAdded from AlertView where Name = 'OpsLogix.IMP.Ping.WMIPingCheck' and Severity = 2 and ResolutionState <> 255")
        row = cursor.fetchall()

        result = []
        if len(row) != 0:
            for item in row:
                age = (datetime.now() - (item['TimeAdded'] + timedelta(hours=3)))
                item = ':x: *{0}* - IP: *{1}* - Age: *{2} Days {3} Hours {4} Minutes*'.format(item['MonitoringObjectDisplayName'],
                                                                                        item['MonitoringObjectName'],
                                                                                        age.days, (age.seconds // 3600),
                                                                                        (age.seconds // 60) % 60)
                result.append(item)

            message.reply('' + "\n".join(result))
            # print(result)
            conn.close()
        else:
            message.reply('Все принтеры are воркинг пёрфектли. МГИМО ФИНИШД!')
    else:
        message.reply(text_messages['if_not_admin'])


@respond_to('device (.*)')
def device(message, something):
        # take username from reply
    """
    details = ""
    details += "text = '{}'\n".format(message.body["text"])
    details += "ts = '{}'\n".format(message.body["ts"])
    details += "user id = '{}'\n".format(message.body["user"])
    details += "user name = '{}'\n".format(message._client.users.get(message.body["user"])["name"])
    details += "team id = '{}'\n".format(message.body["team"])
    details += "type = '{}'\n".format(message.body["type"])
    details += "channel = '{}'\n".format(message.body["channel"])
    """
    username = "{}".format(message._client.users.get(message.body["user"])["name"])

    # check admin permissions
    if username in admin_list:
        # create objects
        db = database()
        # print(something)
        # execute sql

        sql = ("""
                                  SELECT 
                                        status_id,
                                        asset_tag,
                                        last_name,
                                        first_name,
                                        username,
                                        jobtitle,
                                        serial
                                  FROM assets
                                     inner join users on assets.assigned_to = users.id
                                  where assets.asset_tag like %s
                                        """)
        db.execute(sql, something)
        # print(db.sql_result)
        # print(type(db.sql_result))


        # if we caught two or more row from the sql query
        finaltext = []

        if len(db.sql_result) != 0:
            for item in db.sql_result:
                item = '{0} | {1} {2} | {3} | {4} | s/n: {5}'.format(item['asset_tag'], item['last_name'], item['first_name'], item['username'], item['jobtitle'], item['serial'])
                finaltext.append(item)
            # print(finaltext)
            message.reply('```' + "\n".join(finaltext) + '```')
        else:
            # проверям девайсы на складе
            sql = ("""
            SELECT 
            asset_tag,
            serial,
            status_id
            FROM assets
            where assets.asset_tag like %s
                   """)
            db.execute(sql, something)
            # если выше вернуло 0, проверяем еще раз на складе, если опять вернуло 0, ну значит не судьба
            if len(db.sql_result) != 0:
                for item in db.sql_result:
                    item = '{0} | s/n: {1} - на складе'.format(item['asset_tag'], item['serial'])
                    finaltext.append(item)
                message.reply('```' + "\n".join(finaltext) + '```')
            else:
                message.reply("I cannot find anything in the the database")

        """
        if (len(db.sql_result) != 0) and ((db.sql_result[0][0] == 4) or (db.sql_result[0][0] == 2)):
            for item in db.sql_result:
                item = ((', ').join(map(str, db.sql_result)))
                finaltext.append(item + '\n')

            print(finaltext)

            message.reply(":computer: {0} на складе".format(finaltext))

        elif (len(db.sql_result) != 0) and ((db.sql_result[0][0] != 4) or (db.sql_result[0][0] != 2)):
            for item in db.sql_result:
                item = ((' ').join(map(str, item)))
                finaltext.append(item + '\n')

            message.reply(":computer: ".join(finaltext))
        """

    else:
        message.reply(text_messages['if_not_admin'])

    db.close()


# ищем по фамилии с русскими буквами
@respond_to('user (.*[а-яА-Я].*)')
def device(message, something):
    # take username from reply
    username = "{}".format(message._client.users.get(message.body["user"])["name"])

    # check admin permissions
    if username in admin_list:
        # create objects
        db = database()
        # print(something)
        # execute sql

        sql = ("""      
      SELECT
      asset_tag,
      serial,
      last_name,
      first_name,
      username,
      jobtitle,
      models.name

      FROM assets
      inner join users on assets.assigned_to = users.id
      inner join models on assets.model_id = models.id
      where last_name like %s
                                        """)
        db.execute(sql, something)

        # if we caught two or more row from sql query
        finaltext = []
        if len(db.sql_result) != 0:
            grouped_result = {}
            for elem in db.sql_result:
                grouped_result.setdefault((elem['last_name'], elem['first_name'], elem['username'], elem['jobtitle']),
                                          []).append(
                    (elem['asset_tag'], elem['name'], elem['serial']))
            for username in grouped_result:
                item2 = " ".join(username)
                finaltext.append(item2)
                for item in grouped_result[username]:
                    item = " | ".join(item)
                    finaltext.append(item)

            message.reply('```' + "\n".join(finaltext) + '```')

        else:
            message.reply("I cannot find anything in the database")

    else:
        message.reply(text_messages['if_not_admin'])

    db.close()


# ищем по логину
@respond_to('user (.*[a-zA-Z].*)')
def device(message, something):
        # take username from reply
    username = "{}".format(message._client.users.get(message.body["user"])["name"])

    # check admin permissions
    if username in admin_list:
        # create objects
        db = database()
        # print(something)
        # execute sql

        sql = ("""      
      SELECT
      asset_tag,
      serial,
      last_name,
      first_name,
      username,
      jobtitle,
      models.name
                                        
      FROM assets
      inner join users on assets.assigned_to = users.id
      inner join models on assets.model_id = models.id
      where username like %s
                                        """)
        db.execute(sql, something)

        # if we caught two or more row from sql query
        finaltext = []
        if len(db.sql_result) != 0:
            grouped_result = {}
            for elem in db.sql_result:
                grouped_result.setdefault((elem['last_name'], elem['first_name'], elem['username'], elem['jobtitle']),
                                          []).append(
                    (elem['asset_tag'], elem['name'], elem['serial']))
            for username in grouped_result:
                item2 = " ".join(username)
                finaltext.append(item2)
                for item in grouped_result[username]:
                    item = " | ".join(item)
                    finaltext.append(item)

            message.reply('```' + "\n".join(finaltext) + '```')

        else:
            message.reply("I cannot find anything in the database")

    else:
        message.reply(text_messages['if_not_admin'])

    db.close()


@respond_to('store (.*)')
def store_results(message, something):
    # take username from reply
    username = "{}".format(message._client.users.get(message.body["user"])["name"])

    sql = ("""
    select 
    models.name,
    count(models.name) as count
    from ormdb.assets
    inner join models on assets.model_id = models.id
    where models.category_id = %s
    
    and assigned_to is null
    and (assets.status_id = 2 or assets.status_id = 4)
    group by models.name
    order by count(models.name) desc
        """)

    # check admin permissions
    if username in admin_list:
        # create objects
        db = database()
        finaltext = []

        # notebooks
        if something == 'nb':
            something = 2
            db.execute(sql, something)
            for item in db.sql_result:
                item = '*{0}* - {1}'.format(item['count'], item['name'])
                finaltext.append(item)
            # print(finaltext)
            message.reply("\n".join(finaltext))

        # desktop
        elif something == 'dt':
            something = 3
            db.execute(sql, something)
            for item in db.sql_result:
                item = '*{0}* - {1}'.format(item['count'], item['name'])
                finaltext.append(item)
            message.reply("\n".join(finaltext))

        # mac os
        elif something == 'mac':
            something = 7
            db.execute(sql, something)
            for item in db.sql_result:
                item = '*{0}* - {1}'.format(item['count'], item['name'])
                finaltext.append(item)
            message.reply("\n".join(finaltext))

        # monoblock
        elif something == 'mb':
            something = 4
            db.execute(sql, something)
            for item in db.sql_result:
                item = '*{0}* - {1}'.format(item['count'], item['name'])
                finaltext.append(item)
            message.reply("\n".join(finaltext))

        elif something == 'mn':
            something = 1
            db.execute(sql, something)
            for item in db.sql_result:
                item = '*{0}* - {1}'.format(item['count'], item['name'])
                finaltext.append(item)
            message.reply("\n".join(finaltext))

        else:
            message.reply('Неверная команда, попробуйте @iprobot store *nb*/*dt*/*mac*/*mb*/*mn*\nnb - notebook, dt - desktop, mac - apple, mb - monoblock(all-in-one), mn - monitor')

    else:
        message.reply(text_messages['if_not_admin'])

    db.close()


if __name__ == "__main__":
    main()
