import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime
from pathlib import Path


def siguiente_referencia(): #Función generadora de referencias Fecha y contador
    archivo = Path("contadorSPEI.txt")

    if archivo.exists(): #Checa si el archivo existe
        contador = int(archivo.read_text())
    else:
        contador = 0

    contador += 1
    archivo.write_text(str(contador))

    fecha = datetime.now().strftime("%Y%m%d")

    return f"REF-{fecha}-{contador:04d}"

def Identificador(): #Funcion para generar el identificador del documento
    archivo = Path("IDENTIFICADOR UNICO.txt")

    if archivo.exists():
        contador = int(archivo.read_text())#Checa si el archivo existe
    else:
        contador = 0

    contador += 1
    archivo.write_text(str(contador))
    
    fecha = datetime.now().strftime("%Y%m%d")

    return f"Referencia-{contador}-{fecha}"

def generar_xml( #Es la funcion para generar el XML y se declaran los campos a usar
    msg_id,
    fecha_hora,
    Referencia_pago,
    fecha_ejecucion,
    Nombre_compañia,
    Calle_compañia,
    CP_compañia,
    Compañia_ciudad,
    cuenta_ordenante,
    bic_banco,
    referencia_unica,
    monto,
    Nombre_benificiario,
    Calle_benificiario,
    CP_benificiario,
    Ciudad_benificiario,
    cuenta_beneficiario,
    end_to_end_id=None    # Opcional: referencia entregada al beneficiario (distinta de referencia_unica).
                          # Si no se provee, usa el mismo valor de referencia_unica (comportamiento anterior).
                          # InstrId (referencia_unica) mapea en el estado de cuenta HSBC.
                          # EndToEndId (end_to_end_id) es la referencia que recibe el beneficiario.
):


    #Tipo de archivo
    document = ET.Element(
        "Document",
        {
            "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "xmlns": "urn:iso:std:iso:20022:tech:xsd:pain.001.001.03"
        }
    )

    cstmr = ET.SubElement(document, "CstmrCdtTrfInitn")

    # Header
    grp = ET.SubElement(cstmr, "GrpHdr")

    ET.SubElement(grp, "MsgId").text = msg_id 
    ET.SubElement(grp, "CreDtTm").text = fecha_hora

    ET.SubElement(grp, "NbOfTxs").text = "1"
    ET.SubElement(grp, "CtrlSum").text = str(monto)

    initg = ET.SubElement(grp, "InitgPty")
    id1 = ET.SubElement(initg, "Id")
    org = ET.SubElement(id1, "OrgId")
    othr = ET.SubElement(org, "Othr")
    ET.SubElement(othr, "Id").text = "PC000032364" #Este numero sera cambiado cuando se habilite el servico con el banco

    # Info pago
    ptm = ET.SubElement(cstmr,"PmtInf")

    # Referencia de pago
    pmt_inf_id = ET.SubElement(ptm, "PmtInfId")
    pmt_inf_id.text = Referencia_pago

    # Método de pago
    pmt_mtd = ET.SubElement(ptm, "PmtMtd")
    pmt_mtd.text = "TRF"

    # Tipo de pago
    pmt_tp_inf = ET.SubElement(ptm, "PmtTpInf")
    svc_lvl = ET.SubElement(pmt_tp_inf, "SvcLvl")
    cd = ET.SubElement(svc_lvl, "Cd")
    cd.text = "URGP"

    # Fecha ejecución
    reqd_exctn_dt = ET.SubElement(ptm, "ReqdExctnDt")
    reqd_exctn_dt.text = fecha_ejecucion

    # Ordenante
    dbtr = ET.SubElement(ptm, "Dbtr")
    nm = ET.SubElement(dbtr, "Nm")
    nm.text = Nombre_compañia

    pstl_adr = ET.SubElement(dbtr, "PstlAdr")

    #Calle principal
    strt_nm = ET.SubElement(pstl_adr, "StrtNm")
    strt_nm.text = Calle_compañia
    
    #Codigo postal
    pst_cd = ET.SubElement(pstl_adr, "PstCd")
    pst_cd.text = CP_compañia
    
    #Ciudad
    twn_nm = ET.SubElement(pstl_adr, "TwnNm")
    twn_nm.text = Compañia_ciudad

    ctry = ET.SubElement(pstl_adr, "Ctry")
    ctry.text = "MX"

    # Cuenta ordenante
    dbtr_acct = ET.SubElement(ptm, "DbtrAcct")
    acct_id = ET.SubElement(dbtr_acct, "Id")
    othr = ET.SubElement(acct_id, "Othr")

    acct_number = ET.SubElement(othr, "Id")
    acct_number.text = cuenta_ordenante

    # Banco ordenante
    dbtr_agt = ET.SubElement(ptm, "DbtrAgt")
    fin_instn_id = ET.SubElement(dbtr_agt, "FinInstnId")

    bic = ET.SubElement(fin_instn_id, "BIC")
    bic.text = bic_banco

    pstl_adr_bank = ET.SubElement(fin_instn_id, "PstlAdr")
    bank_country = ET.SubElement(pstl_adr_bank, "Ctry")
    bank_country.text = "MX"



    # Transferencia
    cdt_trf_tx_inf = ET.SubElement(ptm, "CdtTrfTxInf")

    # IDs
    pmt_id = ET.SubElement(cdt_trf_tx_inf, "PmtId")

    # InstrId: referencia interna que HSBC mapea en el ESTADO DE CUENTA del ordenante.
    instr_id = ET.SubElement(pmt_id, "InstrId")
    instr_id.text = referencia_unica

    # EndToEndId: referencia que se ENTREGA AL BENEFICIARIO en su estado de cuenta.
    # Si no se provee end_to_end_id, usa la misma referencia_unica (compatible con versión anterior).
    end_to_end = ET.SubElement(pmt_id, "EndToEndId")
    end_to_end.text = end_to_end_id if end_to_end_id is not None else referencia_unica

    # Monto
    amt = ET.SubElement(cdt_trf_tx_inf, "Amt")

    instd_amt = ET.SubElement(amt, "InstdAmt")
    instd_amt.set("Ccy", "MXN")
    instd_amt.text = str(monto)

    # Banco beneficiario
    cdtr_agt = ET.SubElement(cdt_trf_tx_inf, "CdtrAgt")
    fin_instn_id2 = ET.SubElement(cdtr_agt, "FinInstnId")

    clr_sys = ET.SubElement(fin_instn_id2, "ClrSysMmbId")
    mmb_id = ET.SubElement(clr_sys, "MmbId")
    mmb_id.text = "021" #

    pstl_adr2 = ET.SubElement(fin_instn_id2, "PstlAdr")
    ctry2 = ET.SubElement(pstl_adr2, "Ctry")
    ctry2.text = "MX"

    # Beneficiario
    cdtr = ET.SubElement(cdt_trf_tx_inf, "Cdtr")

    nm2 = ET.SubElement(cdtr, "Nm")
    nm2.text = Nombre_benificiario

    pstl_adr3 = ET.SubElement(cdtr, "PstlAdr")

    strt_nm2 = ET.SubElement(pstl_adr3, "StrtNm")
    strt_nm2.text = Calle_benificiario

    pst_cd2 = ET.SubElement(pstl_adr3, "PstCd")
    pst_cd2.text = CP_benificiario

    twn_nm2 = ET.SubElement(pstl_adr3, "TwnNm")
    twn_nm2.text = Ciudad_benificiario

    ctry3 = ET.SubElement(pstl_adr3, "Ctry")
    ctry3.text = "MX"

    # Cuenta beneficiario
    cdtr_acct = ET.SubElement(cdt_trf_tx_inf, "CdtrAcct")

    acct_id2 = ET.SubElement(cdtr_acct, "Id")
    othr2 = ET.SubElement(acct_id2, "Othr")

    acct_number2 = ET.SubElement(othr2, "Id")
    acct_number2.text = cuenta_beneficiario

    # Formatear XML bonito
    xml_bytes = ET.tostring(document, encoding="UTF-8")
    pretty_xml = minidom.parseString(xml_bytes).toprettyxml(indent="    ",encoding="UTF-8")

    # HSBC requiere espacio antes de ?> en la declaracion XML
    pretty_xml = pretty_xml.replace(
        b'<?xml version="1.0" encoding="UTF-8"?>',
        b'<?xml version="1.0" encoding="UTF-8" ?>',
        1
    )

    # Guardar archivo
    with open(referencia_unica+".xml", "wb") as f:
        f.write(pretty_xml)

    print("XML "+ referencia_unica +" generado correctamente")


# EJEMPLO DE USO
generar_xml(
    msg_id=Identificador(), #Identificador del documento (No repetir en un periodo de 6 meses) 
    fecha_hora=datetime.now().strftime("%Y-%m-%dT%H:%M:%S"), #Fecha y hora actual
    Referencia_pago="PAYMENT123", #Identificador interno que podemos revisar (ejemplo una orden de compra como P10290) 
    fecha_ejecucion=datetime.now().strftime("%Y-%m-%d"), #Fecha en la que se realizara el pago
    Nombre_compañia="MI EMPRESA SA DE CV",
    Calle_compañia="Av Principal 123",
    CP_compañia="81200",
    Compañia_ciudad="Los Mochis",
    cuenta_ordenante="4043001353",
    bic_banco="BIMEMXMM",
    referencia_unica=siguiente_referencia(), #Referencia unica identificacion facil en caso de auditorias
    monto=0.1, #Cantidad a depositar
    Nombre_benificiario="JUAN PEREZ", #Nombre de a quien se realiza el pago
    Calle_benificiario="Calle Norte 45", #Domicilio
    CP_benificiario="01000", #Codigo Postal
    Ciudad_benificiario="CDMX", #Ciudad en la que esta el domicilio
    cuenta_beneficiario="123456789012345678" #Para los pagos SPEI siempre son 18 digitos
)