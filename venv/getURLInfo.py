import requests
import lxml.html as lh
import sys

def scrapInfo(billno):
    urlbase='https://www.cupost.co.kr/postbox/delivery/localResult.cupost?invoice_no='
    urlbase2='https://www.doortodoor.co.kr/jsp/cmn/TrackingCUpost.jsp?pTdNo='
    print('waybillInfi argument :', billno)

    if len(billno) > 1 :
        url = urlbase + billno.strip()
        url2= urlbase2 + billno.strip()
    else :
        url = urlbase + '6502809121'
        url2= urlbase2 + '6502809121'
    print("URL string:", url)
    #Create a handle, page,  to handle the contents of the website
    page=  requests.get(url)
    page2=   requests.get(url2)
    #Store the contents of the website under doc
    doc = lh.fromstring(page.content)
    doc2= lh.fromstring(page2.content)
    #Parse data that are stored between <tr>..</tr> of HTML
    tr_elements = doc.xpath('//tr')
    tr_elements2= doc2.xpath('//tr')
    #Check the length of the first 12 rows
    [len(T) for T in tr_elements[:22]]

    #Create empty list
    # col=[]
    i=0
    WayBillStr=''
    rWayBill = []
    #For each row, store each first element (header) and an empty list
    for tr_element in tr_elements:
        for t in tr_element:
            i+=1
            name=t.text_content()
            if (i%2 == 0) and (i <= 10) :
                WayBillStr += '"%s"\t' % (name.strip())
                # WayBillStr += '\n'
                # rWayBill.append(name.strip())
            # col.append(name.strip())
            # col.append((name, []))
    print(WayBillStr)
    # print("rWay[]: ",rWayBill.__str__())

    col=[]
    i=0
    TrackStr=""
    for tr_element in tr_elements2:
        for t in tr_element:
            i+=1
            name=t.text_content()
            TrackStr += '"%s"\t'%(name.strip())
            if i/10 < 1 :
                if i%5 == 0 :
                    TrackStr += '\n'
            else :
                if (i-10)%4 == 0 :
                    TrackStr += '\n'
            col.append(name.strip())
    # print('str2[]: ', TrackStr)

    return WayBillStr


if __name__ == "__main__":
    result = scrapInfo(sys.argv[1:])
    print('@main result', result)