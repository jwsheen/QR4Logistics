# ------ fastAPI로 바꿔본다 (flask 프로젝트를) ----
from pydantic import BaseModel
import uvicorn
from fastapi import FastAPI, BackgroundTasks, Depends, Response, Request, File, Form, UploadFile, Header
from typing import Optional

# written by Seneca James W. Sheen 
import getURLInfo

# ------ new added --
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.responses import RedirectResponse as stRedirect

# ------ flask에서 받아온 흔적 ------
import os
import datetime
from jinja2 import Template
from markupsafe import escape
import urllib.request
from werkzeug.utils import secure_filename
from PIL import Image
import glob
from uuid import uuid4
import re
import sys
import subprocess
from pathlib import Path
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

origins = [
    "http://jwsheen.ga",
    "http://bstory.ga",
    "http://localhost:5000",
    "https://bstory.ga",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
import excelIO
# ------ ------ ------
import sqlite3
# ------ ------ ------
conn = ''
curr = ''


# ------ Data 모음이 필요한 것 ----
# WayBillNoBar = 'NA' # 안 쓸 것
# BoxNoQR = 'NA'      # 목적이 사라짐
curWayBillNo = 'NA' # 직전 운송장 번호 유지
productList = []    # 단품 정보 리스트 ={'WayBillNo','NA','productNo','createdAt'} + {product 이미지}
usrStoryList = []   # 구매자나 일반 사용자 = {'productNo','...'} + {productNo 이미지}
donorStoryList = [] # 기부자 사연 = {'WayBillNo','이름*','기부 일자','사연[3]'} + {waybill 이미지, product 이미지}
waybillList = []    # 운송장 리스트 = {'WayBillNo','이름*','발송 일자','도착일','createdAt'} + {waybill 이미지}
inputDataQueue = [] # 조립한 input Data
rawScanData = []    # 입력 받은 순서대로 기록( 사건 재구성 근거 = {inputData, timestamp} )
donorBoxPrdList = []   # 운송장=BOX 내용물 ={'WayBillNo','Cat','Product',timestamp}
senderInfoList = [] # 송화인(잠재 기부자) 정보 = {'WayBillNo','송화인','날짜','시간'}
workerStoryList = []
curGeoCity = 'testCity'

if 'posix' in os.name:
    root_path = '/home/iqr/qrdata'
    path_separator = '/'
elif 'nt' in os.name:
    root_path = 'C:/Users/james/PycharmProjects/FastAPI/venv'
    path_separator = '\\'
else:
    root_path = '/home'
    path_separator = '/'
    print('App실행을 위해 root_path를 설정하십시오')

app.mount("/static", StaticFiles(directory="static"), name="static")
# app.mount("/fonts", StaticFiles(directory="fonts"), name="fonts")
# app.mount("/css", StaticFiles(directory="css"), name="css")
# app.mount("/js", StaticFiles(directory="js"), name="js")

templates = Jinja2Templates(directory="templates")


# template = Template("""
# # Generation started on {{ now() }}
# ... this is the rest of my template...
# # Completed generation.
# """)

# template.globals['now'] = datetime.datetime.now()

# ------ image file upload testing at 2020-12-12 20:15
UPLOAD_FOLDER = '/static/uploads/'

secret_key = "secret key"
MAX_CONTENT_LENGTH = 16 * 1024 * 1024

ALLOWED_EXTENSIONS = set(['png', 'jpg', 'jpeg', 'gif'])

@app.on_event("startup")
def init_db():
    global conn, curr

    conn = sqlite3.connect("file:qrData.db?cache=shared",  check_same_thread=False, uri=True) #detect_types=sqlite3.PARSE_DECLTYPES,
    curr = conn.cursor()
    # conn.execute('DROP TABLE IF EXISTS JOBHISTORY')
    conn.execute('CREATE TABLE IF NOT EXISTS jobhistory \
            ( id INTEGER PRIMARY KEY, \
              WayBill CHAR(30), \
              Category CHAR(15), \
              Product CHAR(20), \
              CreatedAt TIMESTAMP, \
              geoCity CHAR(64) \
            )' )
    # conn.execute('DROP TABLE IF EXISTS qrScanInputRaw')
    conn.execute('CREATE TABLE IF NOT EXISTS qrScanInputRaw \
            ( id INTEGER PRIMARY KEY, \
              qrvalue CHAR(30) NOT NULL, \
              createdAt TIMESTAMP, \
              geoCity CHAR(64) \
            )' )

    rowSize = 5
    # load before action data list
    curr.execute('SELECT * FROM qrScanInputRaw')
    # curr = conn.cursor()
    beforeList = curr.fetchall()[- rowSize:]
    for bl in beforeList :
        rawScanData.append(bl[1])
        print('qrscanRaw Data: ', bl[1])
    print("@init_db reload qrScanInputRaw")

    curr.execute('SELECT * FROM jobhistory')
    # curr = conn.cursor()
    beforeList = curr.fetchall()[- rowSize:]
    for bl in beforeList :
        inputDataQueue.append(bl[1:])
        print('jobhistory list: ',bl[1:])
    # conn.execute('ALTER TABLE  qrScanInputRaw\
    #           ADD geoCity CHAR(64) \
    #         ')
    # conn.commit()
    print("@init_db reload jobhistory")

    bckup = sqlite3.connect('file:backup.db',detect_types=sqlite3.PARSE_DECLTYPES,uri=True)
    with bckup:
        conn.backup(bckup)
    # bckup.close()
    # conn.close()
    # --- --- 아래는 어떤 용도로 사용하는지 모름 2021-01-16
    # rc = sqlite3_open("file::memory:?cache=shared", &db);
    # rc = sqlite3_open("file:memdb1?mode=memory&cache=shared", &db);
    return True

@app.on_event("shutdown")
def shutdown_event():
    conn.commit()

    bckup = sqlite3.connect('file:backup.db',detect_types=sqlite3.PARSE_DECLTYPES,uri=True)
    with bckup:
        conn.backup(bckup)
    bckup.close()

    conn.close()

def insJobHistory(productList, geoCity):
    sqlite_insert_with_param = """INSERT INTO jobhistory
                      (WayBill, Category, Product, CreatedAt, geoCity) 
                      VALUES (?, ?, ?, ?, ?);"""

    data_tuple = (productList[0], productList[1],productList[2],productList[3], geoCity)
    curr.execute(sqlite_insert_with_param, data_tuple)

    print('@insJobHistory curr.exec productList ', productList[:4], geoCity)
    conn.commit()

def insertQRIntoTable(qrvalue, createdAt, geoCity):
    sqlite_insert_with_param = """INSERT INTO qrScanInputRaw
                      (qrvalue, createdAt, geoCity) 
                      VALUES (?, ?, ?);"""

    data_tuple = (qrvalue, createdAt, geoCity)
    curr.execute(sqlite_insert_with_param, data_tuple)

    print('@insertQRIntoTable curr.exec qrScanInputRaw ', qrvalue)
    conn.commit()


def make_unique(string):
    ident = uuid4().__str__()[:8]
    return f"{ident}-{string}"

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def chkParity(value):
    # 코드 사용여부는 나중에 결정한다.--parity 실험
    # 'D'+parity+'1CKC'+6byte(19bit) 0 vs O
    byte19 = ['O','1','2','3','5','9','A','B','C','F','G','H','K','L','P','T','U','W','X','Z']
    pList = [3, 0, 5, 7, 17, 7, 5, 3, 13, 11, 5, 11]
    vList = []

    for el in value:
        vList.append(ord(el.lower()) - 96)
    pValue = vList[1]
    print('@parityDonorQr: QRvalue', value)
    print('@parityDonorQr: vList', vList)

    chk = 0
    for x in range(12):
        chk += vList[x] * pList[x]
    parity = chk % 26

    rValue = chr(parity + 96).upper()

    print('@parityDonorQr: chk', chk)
    print('@parityDonorQr: parity', chr(parity + 96).upper())
    if pValue == rValue:
        return True
    else:
        return False

def isWayBill(billNo):
    # CUpost( CU 택배 이용 기부자 )
    cupost = False
    if billNo.isnumeric() and len(billNo) == 10 :
        cupost = True
        return True

    # bstore's registeration ID for DONOR with CUpost before get CUpost WayBillNo
    bStoreID = False
    if billNo.isnumeric() and len(billNo) == 13 :
        bStoreID = True
        return True

    # bstore's DONOR Id for BeautifulStore Offline( 매장 기부자 )
    # parity byte 검증
    DonorID = False
    if any(prefix in billNo for prefix in ('D1CKC', 'DOU3K', 'DOUME','KAB21')):
        # BStore Offline DonorID
        DonorID = True
        return True

    # GS25
    gs25 = False
    # CJ-DaeHan
    cjDaeHan = False
    # DaeSang
    daeSang = False

    return cupost or gs25 or cjDaeHan or daeSang or bStoreID or DonorID

def isProduct(prdNo):
    # ver 1.0 길이와 prefix만 체크한다

    if len(prdNo) == 11 and any(prefix in prdNo for prefix in ('B1AKA','XOBKA')) :
        return True
    else:
        return False

    # isPrdNo = False
    # if prdNo[:5] == 'B1AKA' and len(prdNo) == 11 :
    #     isPrdNo = True
    #
    # if prdNo[:5] == 'XOBKA' and len(prdNo) == 11 :
    #     isPrdNo = True
    #
    # return isPrdNo

def queryCat(CatNo):
    # ver 1.0
    print('@queryCat CatNo:', CatNo)
    Cats = ['NA','cloth','misc','bookCD','electronics']
    return Cats[int(CatNo.strip())]

def aggWorkStory(BillNo):
    iStoryList = []
    for ll in workerStoryList:
        if ll[0] == BillNo:
            iStoryList.append(ll)

    retStoryList = iStoryList
    return retStoryList

def aggBillData(BillNo):
    iDataList = []
    retWBData = []
    # 해당 리스트를 모은다
    for ll in inputDataQueue:
        if ll[0] == BillNo:
            iDataList.append(ll)
    # case1: list[0] 운송장 값만 있는 경우
    # case2: list[0] 운송장 + list[2] 단품 값이 같이 있는 경우
    # case3: list[0] 운송장 + list[1]이 Category?[234] 인 경우
    # 그 외에는 오류로 처리한다
    for dl in iDataList :
        if isWayBill(dl[0]):    # Yes 운송장 = {운송장, *, * }
            if 'Category' in dl[1]:     # Yes 카데고리 {운송장, 카데고리, *}    => 마지막 단품에 카데고리 추가
                if dl[2] == 'NA':
                    if len(retWBData) > 1:
                        retWBData[-1][1] = dl[1]
                else:
                    retWBData.append(dl)    # 완성된 단품
            else:
                if dl[1] == 'NA':       # No 카데고리  {운송장, 'NA', * }
                    # 운송장, 'NA', *?
                    if isProduct(dl[2]):    # Yes 단품    {운송장, 'NA', 단품 }    => 단품
                        retWBData.append(dl)
                    else:                   # No 단품     {운송장, 'NA', 'NA' }   => 운송장
                        retWBData.append(dl)
                else:
                    print('@aggInputQueue DROP Data( Yes, !(Cat|NA), *)', dl)
        else:                   # No 운송장 - 운송장 기록이 없는 기록은 버린다
            print('@aggInputQueue DROP Data( No, *, *)', dl)

    return retWBData

# ------ 기부물품 해당 이미지 모두 찾아서 최근 올린 것을 골라내기 ----
def getFileName(filename: str):
    searchDir = UPLOAD_FOLDER
    file_list = []
    print('find filename: ', filename.__str__())
    print('OS: %s '%os.name)

    # regex = re.compile('(.*png$)|(.*jpg$)|(.*gif$)')
    # for root, dirs, files in os.walk(searchDir):
    #     for file in files:
    #         # print('file: ',file)
    #         # print('match:', re.search(filename,file))
    #         if re.search(filename,file):
    #             file_list.append(file)

    dir_path = root_path + '/static/uploads/'
    find_key = dir_path + '*' + filename.__str__() + '*'
    print('find files key:', find_key)
    list_of_files = glob.glob(find_key)

    if len(list_of_files) == 0 :
        foundFile =  '2-BeautifulStory.jpg'
        latest_file = 'UnKnown'
    else:
        latest_file = max(list_of_files, key=os.path.getctime)
        foundFile = latest_file.split(path_separator)[-1]
    retFName = '/static/uploads/' + foundFile
    print('OS:%s, founded:%s(%s) '%(os.name, retFName, latest_file))
    # return redirect(url_for('static', filename='uploads/' + foundFile, code=301))
    return {'filename':retFName}



@app.get('/files/{filename}')
def find_files(request: Request,filename: str):
    retName = getFileName(filename).get('filename')
    # searchDir = UPLOAD_FOLDER
    # file_list = []
    # print('find filename: ', filename.__str__())
    # print('OS: %s '%os.name)
    #
    # # regex = re.compile('(.*png$)|(.*jpg$)|(.*gif$)')
    # # for root, dirs, files in os.walk(searchDir):
    # #     for file in files:
    # #         # print('file: ',file)
    # #         # print('match:', re.search(filename,file))
    # #         if re.search(filename,file):
    # #             file_list.append(file)
    #
    # dir_path = root_path + '/static/uploads/'
    # find_key = dir_path + '*' + filename.__str__() + '*'
    # print('find files key:', find_key)
    # list_of_files = glob.glob(find_key)
    #
    # if len(list_of_files) == 0 :
    #     foundFile =  '2-BeautifulStory.jpg'
    #     latest_file = 'UnKnown'
    # else:
    #     latest_file = max(list_of_files, key=os.path.getctime)
    #     foundFile = latest_file.split(path_separator)[-1]
    # retFName = '/static/uploads/' + foundFile
    # print('OS:%s, founded:%s(%s) '%(os.name, retFName, latest_file))
    # # return redirect(url_for('static', filename='uploads/' + foundFile, code=301))
    return {'filename':retFName}
    # referrer = request.headers.get("Referer")
    # return RedirectResponse(referrer,{'name':retFName})
# ----------------------------------------

@app.route('/upload/')
def upload_form():
    return templates('upload.html')

@app.route('/upload_story/', methods=['POST'])
def upload_story():
    referrer = request.headers.get("Referer")
    return RedirectResponse(referrer)

import geoip2.database as geoDB

def getCity(ipaddress: str):
    cityReader = geoDB.Reader("module/GeoLite2-City/GeoLite2-City.mmdb")
    cityResponse = cityReader.city(ipaddress)
    city = cityResponse.city.name
    print('@joblog geoDB ',cityResponse.city.name)
    return city

@app.get('/joblog/')
def joblog(request: Request, name: str, job_story: str, city: str):
    global workerStoryList
    referrer = request.headers.get("Referer")
    # countryReader = geoDB.Reader("module/GeoLite2-Country/GeoLite2-Country.mmdb")
    # countryResponse = countryReader.country('175.125.104.150')
    cityReader = geoDB.Reader("module/GeoLite2-City/GeoLite2-City.mmdb")
    cityResponse = cityReader.city(city)
    print('@joblog geoDB ',cityResponse.city.name)

    iBillNo = name
    iJob_story = job_story
    geoip2city = cityResponse.city.name
    print("before: ",iBillNo,iJob_story,geoip2city)

    if (iJob_story != '') :
        iContents=[iBillNo,iJob_story,geoip2city]
        workerStoryList.append(iContents)

    print('@desc_job referer', referrer)
    urlStr = '/waybill/'+iBillNo
    print('@desc_job urlStr', urlStr)

    return RedirectResponse(referrer)

@app.get('/desc_job/')
def desc_job_old(request: Request, name: str, job_story: str, info: str):
    global workerStoryList
    referrer = request.headers.get("Referer")
    print('@desc_job referrer ', referrer)

    default_value = 'Beautifulstory'
    # iBillNo = request.form.get('name', default_value)
    # iJob_story = request.form.get('job_story', default_value)
    # info = request.form.get('info', default_value)
    iBillNo = name
    iJob_story = job_story
    info = info
    print("before: ",iBillNo,iJob_story)

    if (iJob_story != '') :
        iContents=[iBillNo,iJob_story]
        workerStoryList.append(iContents)
    print('@desc_job referer', referrer)
    urlStr = '/waybill/'+iBillNo
    print('@desc_job urlStr', urlStr)

    return RedirectResponse(referrer)
    # return stRedirect(url=urlStr)

    #     print('Donor Write: ',donorStoryList.__str__())
    #     return templates('donor_story2.html', name=prodname, uStory=workerStoryList, info=info)
    # else:
    #     flash('Null story')
    #     return templates('donor_story2.html', name=prodname, uStory=donorStoryList, info=info)
    #
    # return redirect(referrer)


@app.route('/donor_story/', methods=['POST'])
def donor_story():
    referrer = request.headers.get("Referer")
    default_value = 'Beautifulstory'
    prodname = request.form.get('prod_name', default_value)
    iUser_story = request.form.get('customer_story', default_value)
    iDonor_story = request.form.get('donor_story', default_value)
    info = request.form.get('info', default_value)
    print("before: ",prodname,iUser_story,iDonor_story)

    if (iDonor_story != '') :
        iContents=[prodname,iDonor_story]

        donorStoryList.append(iContents)
        print('Donor Write: ',donorStoryList.__str__())
        return templates('donor_story2.html', name=prodname, uStory=donorStoryList, info=info)
    else:
        flash('Null story')
        return templates('donor_story2.html', name=prodname, uStory=donorStoryList, info=info)

    # return redirect(referrer)


@app.get('/user_story/')
def user_story(request: Request, prod_name: str, customer_story: str, donor_story: Optional[str] = ''):
    global usrStoryList
    default_value = 'Beautifulstory'
    # prodname = request.form.get('prod_name', default_value)
    # iUser_story = request.form.get('customer_story', default_value)
    # iDonor_story = request.form.get('donor_story', default_value)
    productNo = prod_name
    usrStory = customer_story
    iDonor_story = donor_story
    print("before: ",productNo,usrStory,iDonor_story)

    if (usrStory != ''):
        iContents=[productNo,usrStory]
        usrStoryList.append(iContents)
    print('User Write: ',usrStoryList.__str__())

    retUstory = []
    for istr in usrStoryList :
        if istr[0] == productNo :
            retUstory.append(istr)

    # return templates('goods_story.html', name=prodname, uStory=usrStoryList)
    # return templates.TemplateResponse('goods_story.html', {"request": request, , 'uStory': retUstory})
    urlStr = '/products/'+productNo
    print('@user_story urlStr ', urlStr)
    # url = app.url_path_for(urlStr)
    # print('@user_story app.url_ ', url)
    response = stRedirect(url=urlStr)
    return response
    # return redirect(request.headers.get("Referer"))

@app.route('/upload_donors/', methods=['POST'])
@app.route('/upload_images/', methods=['POST'])
def upload_picture():
    referrer = request.headers.get("Referer")
    print('upload_image()-request.url: ',request.url)
    if 'image' not in request.files:
        flash('No file part')
        return redirect(referrer)
    file = request.files['image']
    if file.filename == '':
        flash('No image selected for uploading')
        return redirect(referrer)
    if file and allowed_file(file.filename):
        original_filename = secure_filename(file.filename)

        file_ext = '.' + (original_filename.rsplit('.', 1)[1].lower().__str__())
        default_name = 'UnKnown'
        prodname = request.form.get('prod_name', default_name)
        saving_filename = prodname + file_ext
        unique_filename = make_unique(saving_filename)
        # file.save(os.path.join(UPLOAD_FOLDER, filename))
        file.save(os.path.join(UPLOAD_FOLDER, unique_filename))
        #print(os.path.join(UPLOAD_FOLDER, unique_filename))
        #unique_thumbnail = save_thumbnail(os.path.join(UPLOAD_FOLDER, unique_filename))

        # print('upload_image filename: ' + filename)
        flash('Image successfully uploaded and displayed')
        if 'upload_images' in request.url :
            return templates('donor_story2.html', name=prodname)
        else :
            return templates('upload.html', filename=unique_thumbnail)
            #return templates('upload.html', filename=unique_filename)
    else:
        flash('Allowed image types are -> png, jpg, jpeg, gif')
        return redirect(referrer)

@app.route('/donor_images/', methods=['POST'])
def upload_donorimg():
    referrer = request.headers.get("Referer")

    print('upload_image()-request.url: %s \t referrer: %s'%(request.url,referrer))
    if 'file' not in request.files:
        flash('No file part')
        return redirect(referrer)
    file = request.files['file']
    print("file tag", file)
    if file.filename == '':
        flash('No image selected for uploading')
        return redirect(referrer)

    default_wbNo = 'waybillNo'
    waybillNo = request.form.get('waybillNo', default_wbNo)

    info = ['NA','NA','NA','NA']
    for wb in waybillList:
        if waybillNo == wb[0] :
            info = wb

    if file and allowed_file(file.filename):
        original_filename = secure_filename(file.filename)

        file_ext = '.' + (original_filename.rsplit('.', 1)[1].lower().__str__())
        print('from referrer %s waybillno %s'%( referrer, waybillNo ))

        saving_filename = waybillNo + file_ext
        unique_filename = make_unique(saving_filename)
        # file.save(os.path.join(UPLOAD_FOLDER, filename))
        file.save(os.path.join(UPLOAD_FOLDER, unique_filename))
        print(os.path.join(UPLOAD_FOLDER, unique_filename))
        # unique_thumbnail = save_thumbnail(os.path.join(UPLOAD_FOLDER, unique_filename))

        # print('upload_image filename: ' + filename)
        flash('Image successfully uploaded and displayed')
        if 'waybill_images' in request.url :
            return templates('donor_story2.html', name=waybillNo, filename=unique_filename, info=info)
        else :
            return templates('upload.html', filename=unique_thumbnail)
            #return templates('upload.html', filename=unique_filename)
    else:
        flash('Allowed image types are -> png, jpg, jpeg, gif')
        return redirect(referrer)

import shutil
@app.post('/bill_images/')
async def UploadImage(request: Request, waybillNo: str = Form(...), info: Optional[str] = Form(...), file: UploadFile = File(...)):
    referrer = request.headers.get("Referer")
    # original_filename = secure_filename(file.filename)

    file_ext = '.jpg' # + (original_filename.rsplit('.', 1)[1].lower().__str__())
    print('@UploadImage - from referrer %s waybillno %s' % (referrer, waybillNo))

    saving_filename = waybillNo + file_ext
    unique_filename = make_unique(saving_filename)
    print('@UploadImage root_path ', root_path)
    print('@UploadImage os.path.join~~ ',os.path.join(root_path + UPLOAD_FOLDER, unique_filename))
    # file.filename = unique_filename
    # await file.write()
    uImage = await file.read()
    with open(os.path.join(root_path + UPLOAD_FOLDER, unique_filename), "wb") as buffer:
        buffer.write(uImage)
    #     shutil.copyfileobj(file.file, buffer)
    #
    # # return {"filename": image.filename}
    print('@UploadImage referer ', referrer)
    return RedirectResponse(referrer)
    # urlStr = referrer
    # response = stRedirect(url=urlStr)
    # return response

def upload_waybillimg(request: Request, waybillNo: str, file: UploadFile = File(...),):
    referrer = request.headers.get("Referer")

    print('upload_image()-request.url: %s \t referrer: %s' % (request.url, referrer))
    # if 'file' not in file. request.files:
    if len(file) < 1 :
        flash('No file part')
        return RedirectResponse(referrer)
    # file = request.files['file']
    print("file tag", file)
    if file.filename == '':
        flash('No image selected for uploading')
        return RedirectResponse(referrer)

    default_wbNo = 'waybillNo'
    # waybillNo = request.form.get('waybillNo', default_wbNo)

    info = ['NA', 'NA', 'NA', 'NA']
    for wb in waybillList:
        if waybillNo == wb[0]:
            info = wb

    if file and allowed_file(file.filename):
        original_filename = secure_filename(file.filename)

        file_ext = '.' + (original_filename.rsplit('.', 1)[1].lower().__str__())
        print('from referrer %s waybillno %s' % (referrer, waybillNo))

        saving_filename = waybillNo + file_ext
        unique_filename = make_unique(saving_filename)
        # file.save(os.path.join(UPLOAD_FOLDER, filename))
        file.save(os.path.join(UPLOAD_FOLDER, unique_filename))
        print(os.path.join(UPLOAD_FOLDER, unique_filename))
        # unique_thumbnail = save_thumbnail(os.path.join(UPLOAD_FOLDER, unique_filename))

        # print('upload_image filename: ' + filename)
        flash('Image successfully uploaded and displayed')
        # if 'waybill_images' in request.url:
        #     # return templates.TemplateResponse('waybillData.html', {'name':waybillNo, 'filename':unique_filename, 'info':info})
        #     return RedirectResponse(referrer)
        # else:
        #     return templates.TemplateResponse('upload.html', {'filename':unique_thumbnail})
        #     # return templates('upload.html', filename=unique_filename)
    else:
        flash('Allowed image types are -> png, jpg, jpeg, gif')

    return RedirectResponse(referrer)

@app.get('/upload_users/')
@app.post('/upload_users/')
@app.post('/upload_image/')
async def upload_image(request: Request, prod_name : str = Form(...), file: UploadFile = File(...)):
    referrer = request.headers.get("Referer")
    print('@upload_users request.url: ',request.url)

    file_ext = '.jpg' # + (original_filename.rsplit('.', 1)[1].lower().__str__())
    print('@upload_users - from referrer %s product %s' % (referrer, prod_name))

    saving_filename = prod_name + file_ext
    unique_filename = make_unique(saving_filename)
    print('@upload_users root_path ', root_path)
    print('@upload_users os.path.join~~ ',os.path.join(root_path + UPLOAD_FOLDER, unique_filename))
    # file.filename = unique_filename
    # await file.write()
    uImage = await file.read()
    with open(os.path.join(root_path + UPLOAD_FOLDER, unique_filename), "wb") as buffer:
        buffer.write(uImage)
    #     shutil.copyfileobj(file.file, buffer)
    #
    # # return {"filename": image.filename}
    print('@upload_users referer ', referrer)
    return RedirectResponse(referrer)

def save_thumbnail(infile):
    size = 128, 128

    file, ext = os.path.splitext(infile)
    im = Image.open(infile)
    im.thumbnail(size)
    thumbnail_file = file + ".thumbnail", "JPEG"
    if im.save(thumbnail_file) :
        return thumbnail_file
    return 'BeautifulStory.jpg'

@app.route('/display/<filename>')
def display_image(filename):
    print('display_image filename: ' + filename)
    return redirect(url_for('static', filename='uploads/' + filename), code=301)

####################################################################

@app.route('/')   # URL '/' to be handled by index() route handler
@app.post('/')
async def index(request: Request, user_agent: Optional[str] = Header(None)):
    print('@index request',request, request.headers)
    #inputDataQueue
    return templates.TemplateResponse('getData.html', {"request": request,'dataQueue': inputDataQueue})

@app.route('/getQRData/')
def getQRData(request: Request, user_agent: Optional[str] = Header(None)):
    print('@getQRData  ',user_agent)
    return templates.TemplateResponse('getQRData.html', {"request": request,'prdItem': productList})

@app.route('/getWayBill/')
def getWayBill(request: Request, user_agent: Optional[str] = Header(None)):
    print('@getWayBill ',user_agent)
    return templates.TemplateResponse('getWayBill.html', {"request": request,'wbills':waybillList})

@app.route('/hello/')
def hello(request: Request, name=None):
    id='iqr'
    url = '/'
    # return templates.TemplateResponse('fromNaver.html',{"request": request,'name':name,'id':id,'url':url})
    return templates.TemplateResponse('testIconOnInput.html',{"request": request})


@app.route('/clear/')
def clear(request: Request, name=None):
    global curWayBillNo, BoxNoQR, productList, usrStoryList, donorStoryList, \
        waybillList,inputDataQueue,donorBoxPrdList,senderInfoList

    # WayBillNoBar = 'NA'  # 안 쓸 것
    curWayBillNo = 'NA'  # 직전 운송장 번호 유지
    BoxNoQR = 'NA'  # 목적이 사라짐
    productList = []  # 단품 정보 리스트 ={'WayBillNo','NA','productNo','createdAt'} + {product 이미지}
    usrStoryList = []  # 구매자나 일반 사용자 = {'productNo','...'} + {productNo 이미지}
    donorStoryList = []  # 기부자 사연 = {'WayBillNo','이름*','기부 일자','사연[3]'} + {waybill 이미지, product 이미지}
    waybillList = []  # 운송장 리스트 = {'WayBillNo','이름*','발송 일자','도착일','createdAt'} + {waybill 이미지}

    curWayBillNo = 'NA'  # 직전 운송장 번호 유지
    productList = []  # 단품 정보 리스트 ={'WayBillNo','NA','productNo','createdAt'} + {product 이미지}
    usrStoryList = []  # 구매자나 일반 사용자 = {'productNo','...'} + {productNo 이미지}
    donorStoryList = []  # 기부자 사연 = {'WayBillNo','이름*','기부 일자','사연[3]'} + {waybill 이미지, product 이미지}
    waybillList = []  # 운송장 리스트 = {'WayBillNo','이름*','발송 일자','도착일','createdAt'} + {waybill 이미지}
    inputDataQueue = []  # 입력 받은 순서대로 기록( 사건 재구성 근거 = {inputData, timestamp} )
    donorBoxPrdList = []  # 운송장=BOX 내용물 ={'WayBillNo','Cat','Product',timestamp}
    senderInfoList = []  # 송화인(잠재 기부자) 정보 = {'WayBillNo','송화인','날짜','시간'}
    return redirect('/')

def saveExcel(data):
    xlsx_path = root_path + '/qrdata.xlsx'
    exe_path = root_path +'/excelIO.py'
    if os.path.isfile(exe_path):
        print(".py File exist")
        # resultIO = subprocess.check_output([sys.executable, "excelIO.py", data])
        resultIO = subprocess.call([sys.executable,'./excelIO.py', data[0], data[1],data[2],data[3]])
        # resultStr = resultIO.decode().replace('\t', ' ').replace('\n', '').replace('\r', '').replace('"', '')
        print('excelIO: ', resultIO)
    else:
        print('excelIO: 실행 py 화일이 없음')

import time
beforeProcessingTime = time.time()

def timeChecker():
    global beforeProcessingTime, curWayBillNo
    # 입력 idle 10분 지났으면 CLEAR curWayBillNo
    print('@DataQueuing gap :', time.time() - beforeProcessingTime)
    if time.time() - beforeProcessingTime > 600 :
        print('@DataQueuing Time Over')
        curWayBillNo = 'NA'
    else:
        print('Go Go !!!')
    # 작업 시간 기록
    beforeProcessingTime = time.time()
    return

import sqlalchemy
import pandas as pd
dataDF = pd.DataFrame(columns=["WayBill","Category","Product","CreatedAt"],dtype=str)
# init_db()

def DataQueuing(inputData):
    global inputDataQueue, dataDF, curr

    if len(inputDataQueue) > 0 :
        print('@DataQueueing Time Gap',datetime.datetime.now().isoformat(),inputDataQueue[-1][3])
        # clear curWayBillNo

    if (inputData[0] != 'NA') and ('Category' in inputData[1]) and (inputData[2] == 'NA') :
        # 직전 입력된 Product의 Category수정
        inputDataQueue[-1][1] = inputData[1]
        # 해당 Product의 Category를 찾아서 수정
        # print(dataDF.where(dataDF['Product'] == inputData[2]))
        dataDF.iloc[-1, dataDF.columns.get_loc('Category')] = inputData[1]
    else:
        # print('@DataQueuing inputData ',len(inputDataQueue), inputData)
        inputDataQueue.append(inputData)
        # df = pd.DataFrame([inputData], columns=["WayBill","Category","Product","CreatedAt"])
        df = pd.DataFrame([inputData],columns=["WayBill","Category","Product","CreatedAt"])
        # print('@DataQueuing df ',len(df), df)
        dataDF = dataDF.append(df,ignore_index=True).drop_duplicates(subset=['WayBill','Product'],keep='last')
        # df.to_sql('jobhistory', conn, if_exists='append', index=False)
        # curr.execute('SELECT * from jobhistory')
        # print('@DataQueuing curr.exec', curr.fetchall())
        # dataDF = pd.concat(dataDF,df, ignore_index=True)
    print('@DataQueuing dataDF \n ',dataDF)

    return True

def build_List(data) :
    global curWayBillNo, productList, waybillList
    plist = []
    # if ('\b' in data) or ('\t' in data) or ('\n' in data):
    if ('|' in data) or ('\n' in data):
        return False
    else:
        # 일련의 완성된 데이터라면 그대로 ex) ['6709892799','NA','B1AKAX12H1','2020-12-12T12:12:12.123456']
        if (',' in data):
            # print("Befor strip:",data)
            pps = []
            pdata = data.split(',')
            # Data cleasing : space 없는 Data 만들기(.strip())
            for pp in pdata :
                pps.append(pp.strip())
            pdata = pps
            # print('After split:',pdata)

            # --- 과거데이터를 받어서라도 '행위에 근거하여' 운송장 값을 유지한도록 조정한다
            # (1.product) ['NA','NA','B1AKAX12H1','2020-12-12T12:12:12.123456']
            # (2.category) ['NA','NA(Category?2)','NA','2020-12-12T12:12:12.123456']
            # (3.none) ['NA','NA','NA','2020-12-12T12:12:12.123456']
            if pdata[0] == 'NA':
                pdata[0] = curWayBillNo.strip()
            else:
                # (4) ['6709892799','NA','B1AKAX12H1','2020-12-12T12:12:12.123456']
                # 운송장 rule에 맞는 데이터는 curWayBillNo( 현재 작업 중인 박스No )에 담아둔다
                if pdata[0].strip().isnumeric():
                    curWayBillNo = pdata[0].strip()
            # if 'Category' in pdata[1]:
            #     inputDataQueue[-1][1] = pdata[1].rsplit('?',1)[1]

            plist = pdata
            # DataQueuing(plist)
            return plist

        # -----------------------------------------
        # 운송장 6709892799, 단품 B1AKAX12H1 이런 식으로 element 데이터 하나라면 재구성 - 운송장 + 단품 결합

        if ('/' in data):           # URL Data에서 product Data만 떼어낸다
            pdata = data.rsplit("/", 1)[1]
            pdata = pdata.strip()
        else:                       # URL이 아니면 Data 하나만 받는다
            pdata = data.strip()

        # product 단품
        if isProduct(pdata):
            plist = [curWayBillNo,"Category?1",pdata,datetime.datetime.now().isoformat()]
            # plist = [curWayBillNo,"NA",pdata,pdata.json()["datetime"]] # str no json function
            print('@build_List (AddProduct) ', plist)
            # DataQueuing(plist)
            return plist

        # BOX 박스 -- 사용 용도를 아직 모른다 --> 2020.12.24 product로 간주한다.(url은 BOX가 포함되었지만)
        # if ('XOBKA' in pdata):
        #     plist = [curWayBillNo,pdata,"NA",datetime.datetime.now().isoformat()]
        #     return plist

        # 운송장
        if isWayBill(pdata):
            curWayBillNo = pdata
            plist = [curWayBillNo,"NA","NA",datetime.datetime.now().isoformat()]
            # 운송장 리스트에 추가
            print('@build_List (AddWayBill) ', plist)
            waybillList.append(plist)
            # DataQueuing(plist)
            return plist

        # 카테고리
        if 'Category' in pdata :                # 표현식 Category?2
            # pdata = queryCat(pdata.rsplit('?',1)[1])
            plist = [curWayBillNo, pdata, "NA", datetime.datetime.now().isoformat()]
            return plist
        # 모르는 형태
        plist = [curWayBillNo,"NA("+pdata+")","NA",datetime.datetime.now().isoformat()]
        # DataQueuing(plist)
        return plist
    # ----------------
    # 최소 단위 크기로 자른다
    # 2. https://bstory.ga/products/B1AKAOHJR12A https://bstory.ga/products/B1AKAOHJR12E\nhttps://bstory.ga/products/B1AKAOHJR12R
    ## ---- '\b|\t|\n'가 있으면 단위 크기로 자른다
        ## '/'가 있으면 rsplit[0]만 골라 낸다
        # --------'/'로 자르고
        # ------------B1AKA로 구분하는 로직으로 ['운송장','박스','단품','입력시간'] 4자리 list구조로 만들기
        # 1. https://bstory.ga/products/B1AKAOHJR12A
        # ---- '/'로 자르고
        # --------B1AKA로 구분하는 로직으로 ['운송장','박스','단품','입력시간'] 4자리 list구조로 만들기

        ## ','가 있으면 list를 바로 만든다 ##
        # 3. 6700956931,NA,NA,2020-12-18T10:15:09.106344
        # ---- ','로 자르고
        # -------- 그대로 ['운송장','박스','단품','입력시간'] 4자리 list구조로 만들기

            # 4. 6700956931
            # rsplit[0]는 구분 로직에 태워서 list를 완성한다
            # ---- 채워서 ['운송장','박스','단품','입력시간'] 4자리 list구조로 만들기

def write_log(message: str):
    with open("log.txt", mode="a") as log:
        log.write(message)

async def dataProcessing(QRvalue: Optional[str] = None):
    global productList

    prdData = build_List(QRvalue)
    productList.append(prdData)
    DataQueuing(prdData)
    print('@dataProcessing QRdata_[i]: ', prdData)
    print('@dataProcessing dataDF: \n', dataDF)

    rawScanData.append(QRvalue)

    geoCity = curGeoCity
    insJobHistory(prdData, geoCity)
    insertQRIntoTable(QRvalue, datetime.datetime.now().isoformat(), geoCity)
    # prdData = build_List(QRvalue)
    # productList.append(prdData)
    # DataQueuing(prdData)

    return True

def hiddenProcessing(QRvalue: Optional[str] = None):
    global productList

    prdData = build_List(QRvalue)
    productList.append(prdData)
    DataQueuing(prdData)
    print('@dataProcessing QRdata_[i]: ', prdData)
    print('@dataProcessing dataDF: \n', dataDF)

    rawScanData.append(QRvalue)

    geoCity = curGeoCity
    insJobHistory(prdData, geoCity)
    insertQRIntoTable(QRvalue, datetime.datetime.now().isoformat(), geoCity)
    # prdData = build_List(QRvalue)
    # productList.append(prdData)
    # DataQueuing(prdData)

    # return True

@app.get('/version/{id}')
async def show_version(request: Request,id: str=None):
    if id=='james':
        Version='2021-01-27 01'
    else:
        Version='Unknown'

    return Version

@app.get('/qrscan/')
@app.post('/qrscan/')
async def show_qrscan(request: Request, bgTask:  BackgroundTasks, qrdata: str = Form(...), geocity: str = Form(...)):
    global inputDataQueue, curGeoCity
    print('@qrscan ', qrdata, geocity)
    if qrdata is None:
        return templates.TemplateResponse('getData.html', {"request": request, 'dataQueue': inputDataQueue})
    referrer = request.headers.get("Referer")
    remoteIp = request.client.host
    print('@show_qrscan ',referrer, remoteIp)

    # 입력받는대로 저장한다
    # QR_Str = request.form.get('qrdata')
    QR_Str = qrdata.__str__()
    curGeoCity = getCity(geocity)
    print('@show_qrscan QR_Str ', QR_Str, getCity(geocity))
    timeChecker()

    print('QR scaned: DataType %s  %s'%(type(QR_Str), QR_Str))
    # 적절한 크기로 자른다 - space tab enter 모두 잘라낸다
    # if (' ' in QR_Str ) or ('\t' in QR_Str ) or ('\n' in QR_Str ) or ('\b' in QR_Str):
    #     QRvalueSet = re.split(' |\t|\n',QR_Str)

    if ('|' in QR_Str ) or ('\n' in QR_Str ):
        QRvalueSet = re.split('\||\n',QR_Str)
        for QRvalue in QRvalueSet :
            if (QRvalue == 'NA') or (QRvalue == '') :
                continue
            # await dataProcessing(QRvalue)
            bgTask.add_task(hiddenProcessing,QRvalue)
            # background_tasks.add_task(write_log, QRvalue)
            # background_tasks.add_task(dataProcessing, QRvalue)

            # rawScanData.append(QRvalue)
            # prdData = build_List(QRvalue)
            # productList.append(prdData)
            # DataQueuing(prdData)

            # # saveExcel(prdData)
            # # excelIO.queueData(prdData)
            # # if (prdData[0] != 'NA' and prdData[1] == 'NA' and prdData[2] == 'NA' ) :
            # #     waybillList.append(prdData)
            # print('QRdata_[i]: ', prdData)
    else:
        QRvalue = QR_Str
        # background_tasks.add_task(write_log, QRvalue)
        # background_tasks.add_task(dataProcessing, QRvalue)
        bgTask.add_task(hiddenProcessing, QRvalue)
        # await dataProcessing(QRvalue)

        # rawScanData.append(QRvalue)
        # prdData = build_List(QRvalue)
        # productList.append(prdData)
        # DataQueuing(prdData)

        # # if prdData[0] != 'NA':
        # #     waybillList.append(prdData)
        # # saveExcel(prdData)
        # # excelIO.queueData(prdData)
        # print('QRdata_2: ', prdData)

    print('referrer: ',referrer)
    # referrer = request.headers.get("Referer")
    # return RedirectResponse(referrer)
    # return inputDataQueue
    # return True
    return RedirectResponse(referrer)
    # return templates.TemplateResponse('getData.html', {"request": request,'dataQueue': inputDataQueue})

@app.get('/products/{productNo}')
@app.post('/products/{productNo}')
def show_product(request: Request, productNo: str):
    # # 입력받는대로 저장한다
    # productName = request.form.get('product')
    # print('product',productName)
    # prdData = [WayBillNoBar,BoxNoQR,productName,datetime.datetime.now().isoformat()]
    retPrdInfo = []
    for prdItem in inputDataQueue :
        if productNo == prdItem[2] :
            retPrdInfo = prdItem

    for prdItem in listBillProduct :
        if productNo == prdItem[2] :
            retPrdInfo = prdItem
    filename = getFileName(productNo).get('filename')

    retUstory = []
    for istr in usrStoryList:
        if istr[0] == productNo:
            retUstory.append(istr)

    return templates.TemplateResponse('goods_story.html', {"request": request, 'filename': filename, 'info': retPrdInfo, 'uStory': retUstory})

@app.get('/prd/{productNo}')
@app.post('/prd/{productNo}')
def show_product(request: Request, productNo: str):
    # # 입력받는대로 저장한다
    # productName = request.form.get('product')
    # print('product',productName)
    # prdData = [WayBillNoBar,BoxNoQR,productName,datetime.datetime.now().isoformat()]
    retPrdInfo = []
    for prdItem in inputDataQueue :
        if productNo == prdItem[2] :
            retPrdInfo = prdItem

    for prdItem in listBillProduct :
        if productNo == prdItem[2] :
            retPrdInfo = prdItem
    filename = getFileName(productNo).get('filename')

    retUstory = []
    for istr in usrStoryList:
        if istr[0] == productNo:
            retUstory.append(istr)

    return templates.TemplateResponse('goods_story_storyimage.html', {"request": request, 'filename': filename, 'info': retPrdInfo, 'uStory': retUstory})

# DONOR 페이지는 운송장(waybill) 페이지를 포함 한다. 기부자(매장, 택배, 수거?)는 DONOR페이지를 본다.
# 입고 작업자는 작업자 페이지를 따로 본다( 입고 처리자는 DONOR 입장+ 물품 수령자 입장을 갖는다 )
# 입고 작업자(되살림터, 매장)는 작업 결과를 볼 수 있다( 일일 물품기부는 N건이고, 기부건/ 기부물품 수량 / 기부자 / 접수시간을 본다 ) + a(geoIP)
@app.route('/box/<boxQR>')
@app.route('/BOX/<boxQR>')
def show_donor(request: Request, dornorQR: str):
    # BoxNoQR = boxQR
    # prdData = [0,boxQR,0,datetime.datetime.now().isoformat()]
    for prdItem in inputDataQueue :
        if donorQR == prdItem[0]:
            return templates.TemplateResponse('goods_story.html', {"request": request, 'filename': donorQR, 'info': retPrdInfo, 'uStory': retUstory})
    # productList.append(prdData)
    # printList(productList)

    return templates.TemplateResponse('contentsInBox.html', {"request": request,'name':donorQR, 'filename':filename,'info':aBillInfo, 'list':bnList, 'jStory':wnList, 'cat':Cat})

@app.route('/wbdata/<waybillNo>')
@app.route('/WBDATA/<waybillNo>')
def show_wbdata(waybillNo):
    #     onBill = False
    #     # for wb in waybillList:
    #     #     if wb[0] == waybillNo:
    #     #         onBill = True
    #     #         anWayBill = wb
    # #    if not onBill :
    s2_out = getURLInfo.scrapInfo(waybillNo)
    my_string = s2_out.replace('\t',' ').replace('\n','').replace('\r','').replace('"','')
    anWayBill = my_string.split(' ')
    print("@wbdata/ return s2_out:",anWayBill)
    waybillList.append(anWayBill)
    # wblist= filter(waybillNo, waybillList)
    print('@wbdata waybill info: ',anWayBill)
    return templates('waybillData.html',name=waybillNo,info=anWayBill)

def removeDuplicate(listData):
    alist = []
    for list in listData:
        notExist = True
        for ll in alist :
            if list[0:3] == ll[0:3] :
                notExist = False

        if notExist:
            alist.append(list)
    # print ('list ', alist)
    return alist

def getSenderInfo(BillNo):
    global senderInfoList
    aBillInfo = ''

    # TEST : WayBill은 무조건 있는 상태로
    wasBillInfo = False
    for ww in senderInfoList:
        if ww[0] == BillNo:
            wasBillInfo = True
            aBillInfo = ww
    print("@getSenderInfo in wasBillInfo:", aBillInfo)

    if not wasBillInfo:
        s2_out =  getURLInfo.scrapInfo(BillNo)
        my_string = s2_out.replace('\t', ' ').replace('\n', '').replace('\r', '').replace('"', '')
        aBillInfo = my_string.split(' ')
        print("@getSenderInfo return s2_out:", aBillInfo)
        senderInfoList.append(aBillInfo)

    return aBillInfo

listBillProduct=[]

@app.get('/DONOR/{donorID}')
@app.post('/DONOR/{donorID}')
def donorPage(request: Request, donorID: str):
    global listBillProduct

    # 운송장 정보 검색한 것
    # anList = []
    print('@show_waybill BillNo', donorID)
    anList = aggBillData(donorID)
    # bnList = removeDuplicate(anList)
    wnList = aggWorkStory(donorID)
    df = dataDF[dataDF["WayBill"] == donorID]

    # CatList = df["Category"].value_counts()
    # print('@show_waybill BOX(waybill) df \n', CatList)
    # print('@show_waybill BOX(waybill) df cc[:] \n')
    # for cc in CatList:
    #     print(cc[0],cc[1])

    Cat = [0,0,0,0]
    for v in df["Category"].value_counts().index :
        if 'Category?1' in v:
            Cat[0] = df["Category"].value_counts()[v]
        if 'Category?2' in v:
            Cat[1] = df["Category"].value_counts()[v]
        if 'Category?3' in v:
            Cat[2] = df["Category"].value_counts()[v]
        if 'Category?4' in v:
            Cat[3] = df["Category"].value_counts()[v]

    print('@show_waybill Cat List', Cat)

    # df.values.tolist
    bnList = df.to_numpy().tolist()
    print('@show_waybill BOX(waybill) bnlist \n', bnList)
    # 보관하고 있을 것이다? DataQueue에서 읽어서 background에서 찾아 놓았을 것이다...

    # 운송장(=BOX) 에서 읽은 단품 리스트(with Category)
    # DataQueue에서 읽어내면 리스트는 뽑아낼 수 있다
    # # Data를 깔끔(중복제거, Category 정돈)하게 만든다.
    for bn in bnList :
        listBillProduct.append(bn)
    # aBillInfo = [운송장번호, '', '발송일자','발송시간','이*름']
    aBillInfo = [donorID, '', datetime.datetime.now().strftime('%Y-%m-%d'),'발송시간','기부자']
    filename = getFileName(donorID).get('filename')
    print('@show_waybill filename ', filename)
    # return templates('donor_story2.html',name=waybillNo, info=oneWayBill, list=bnList)
    # return templates('contentsInBox.html', name=waybillNo, info=aBillInfo, list=bnList, jStory=wnList)
    return templates.TemplateResponse('donorPage.html', {"request": request,'name':donorID, 'filename':filename,'info':aBillInfo, 'list':bnList, 'jStory':wnList, 'cat':Cat})


@app.get('/waybill/{waybillNo}')
@app.post('/waybill/{waybillNo}')
def show_waybill(request: Request, waybillNo: str):
    global listBillProduct

    # 운송장 정보 검색한 것
    # anList = []
    print('@show_waybill BillNo', waybillNo)
    anList = aggBillData(waybillNo)
    # bnList = removeDuplicate(anList)
    wnList = aggWorkStory(waybillNo)
    df = dataDF[dataDF["WayBill"] == waybillNo]
    # print('@show_waybill BOX(waybill) df \n', df["Category"].value_counts())

    # CatList = df[["Category"]].value_counts()
    # print('@show_waybill BOX(waybill) df \n', CatList)
    # print('@show_waybill BOX(waybill) df cc[:] \n')
    #
    # # Cat = [CatList["Category?1"],CatList["Category?2"],CatList["Category?3"],CatList["Category?4"]]
    # # print('@show_waybill Cat List first', Cat)

    Cat = [0,0,0,0]
    for v in df["Category"].value_counts().index :
        if 'Category?1' in v:
            Cat[0] = df["Category"].value_counts()[v]
        if 'Category?2' in v:
            Cat[1] = df["Category"].value_counts()[v]
        if 'Category?3' in v:
            Cat[2] = df["Category"].value_counts()[v]
        if 'Category?4' in v:
            Cat[3] = df["Category"].value_counts()[v]

    print('@show_waybill Cat List last', Cat)

    # df.values.tolist
    bnList = df.to_numpy().tolist()
    print('@show_waybill BOX(waybill) bnlist \n', bnList)
    # 보관하고 있을 것이다? DataQueue에서 읽어서 background에서 찾아 놓았을 것이다...

    # 운송장(=BOX) 에서 읽은 단품 리스트(with Category)
    # DataQueue에서 읽어내면 리스트는 뽑아낼 수 있다
    # # Data를 깔끔(중복제거, Category 정돈)하게 만든다.
    for bn in bnList :
        listBillProduct.append(bn)

    aBillInfo = getSenderInfo(waybillNo)
    filename = getFileName(waybillNo).get('filename')
    print('@show_waybill filename ', filename)
    # return templates('donor_story2.html',name=waybillNo, info=oneWayBill, list=bnList)
    # return templates('contentsInBox.html', name=waybillNo, info=aBillInfo, list=bnList, jStory=wnList)
    return templates.TemplateResponse('contentsInBox.html', {"request": request,'name':waybillNo, 'filename':filename,'info':aBillInfo, 'list':bnList, 'jStory':wnList, 'cat':Cat})

@app.get('/print/')
@app.route('/print/')
def print_List(request: Request):
    referrer = request.headers.get("Referer")
    print(referrer)

    curr.execute('SELECT * from jobhistory')
    printList = curr.fetchall()

    # return templates('listingData.html', prdItem=productList, referrerURL=referrer)
    # return templates.TemplateResponse('listingData.html', {"request": request,'prdItem':productList, 'referrerURL':referrer})
    return templates.TemplateResponse('listingData.html', {"request": request,'prdItem':printList, 'referrerURL':referrer})
    # return escape(productList)

@app.get('/rawdata/')
@app.route('/rawdata/')
def print_List(request: Request):
    referrer = request.headers.get("Referer")
    print(referrer)

    curr.execute('SELECT * from qrScanInputRaw')
    printList = curr.fetchall()

    # return templates('listingData.html', prdItem=productList, referrerURL=referrer)
    return templates.TemplateResponse('listingData.html', {"request": request,'prdItem':printList, 'referrerURL':referrer})
    # return escape(productList)

# ----------------------------------------------------------------------
# 공부할 것( 입력하고 피드백 하기 )
# @app.route('/recieve_data')# https://realpython.com/flask-by-example-part-3-text-processing-with-requests-beautifulsoup-nltk/

# command url
# 되살림터, 매장 기부물품 수령/접수 - 정보 저장
@app.route('/receive/',methods=['GET', 'POST'])
def receive():
    headers = Flask.request_class.headers
    print(headers)
    return templates('getQRData.html', prdItem=productList)


# 매장에서 상품 입고 - 재고 증가
@app.route('/instock/',methods=['GET', 'POST'])
def instock():
    return templates('testing.html', tCode='매장입고')


# 매장에서 판매 - 현금 증가, 재고 감소 - 고객 구매 영수증 발급(고객 반품시 사용)
@app.route('/sell/',methods=['GET', 'POST'])
def sell():
    return templates('testing.html', tCode='매장판매')


# 고객이 반품 - 고객 반품 QR - 현금 감소, 재고 증가
@app.route('/takeback/',methods=['GET', 'POST'])
def takeback():
    return templates('testing.html', tCode='고객반품')

# ----------------------------------------------------------------------
def redirect_url(default='index'):
    return request.args.get('next') or \
           request.referrer or \
           url_for(default)
# ---------------------------------------------------------------------

import api
app.include_router(api.router, tags=["Services"], prefix="")

if __name__ == '__main__':  # Script executed directly?
    # app.run(host="0.0.0.0", port=8000)  # Launch built-in web server and run this Flask webapp
    # app.run(host="0.0.0.0")  # Launch SSL

    uvicorn.run('iQr:app', port=5000, host='0.0.0.0', reload=True, debug=True, workers=2)

# TODO: excel화일에 입출력
# TODO: html response + async 기능 만들기
# TODO: asyncio로 excel IO 만들어 넣기
