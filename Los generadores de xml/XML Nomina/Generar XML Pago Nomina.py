from decimal import Decimal, InvalidOperation
import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime
from pathlib import Path

# Función para formatear montos en el formato requerido por el XML
def monto_xml(valor):
    try: 
        monto = Decimal(str(valor)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"Monto invalido: {valor!r}") from error
    if monto <= 0:
        raise ValueError("El monto debe ser mayor que cero.")
    return f"{monto:.2f}"

# Función para validar que la transferencia cumpla con los requisitos de nomina HSBC
def validar_transferencia(transferencia):
    if str(transferencia["banco"]) != "021":
        raise ValueError("La nomina HSBC debe usar el banco beneficiario 021.")
    cuenta = str(transferencia["cuenta"])
    if len(cuenta) != 10 or not cuenta.isdigit():
        raise ValueError("La cuenta beneficiaria de nomina HSBC debe tener 10 digitos.")


def siguiente_referencia(): #Función generadora de referencias con Fecha y contador
    archivo = Path("contadorNOMINA.txt")

    if archivo.exists(): #Checa si el archivo existe
        contador = int(archivo.read_text())
    else:
        contador = 0

    contador += 1
    archivo.write_text(str(contador))

    fecha = datetime.now().strftime("%Y%m%d")

    return f"NOMINA{fecha}{contador:04d}"

def Identificador(): #Funcion para generar el identificador del documento
    archivo = Path("IDENTIFICADOR_UNICO_NOMINA.txt")

    if archivo.exists():
        contador = int(archivo.read_text())#Checa si el archivo existe
    else:
        contador = 0

    contador += 1
    archivo.write_text(str(contador))
    
    fecha = datetime.now().strftime("%Y%m%d")

    return f"ReferenciaNomina-{contador}-{fecha}"

def generar_xml( #Es la funcion para generar el XML y se declaran los campos a usar
    msg_id, #Identificador del documento (No repetir en un periodo de 6 meses)
    fecha_hora,
    Referencia_pago,
    fecha_ejecucion,
    Nombre_compañia,
    Calle_compañia,
    CP_compañia,
    Colonia_Compañia,
    Ciudad_compañia,
    cuenta_ordenante,
    bic_banco,
    referencia_unica,

    transferencias
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

    # Validar cada transferencia antes de continuar
    for transferencia in transferencias:
        validar_transferencia(transferencia)

    ET.SubElement(grp, "NbOfTxs").text = str(len(transferencias))
    # Calcula la suma total de los montos de las transferencias
    total = sum(Decimal(str(t["monto"])) for t in transferencias)
    # Registra la suma total de las transferencias en el formato requerido por el XML
    ET.SubElement(grp, "CtrlSum").text = monto_xml(total)

    initg = ET.SubElement(grp, "InitgPty")
    id1 = ET.SubElement(initg, "Id")
    org = ET.SubElement(id1, "OrgId")
    othr = ET.SubElement(org, "Othr")
    ET.SubElement(othr, "Id").text = "PC000032364" #Este numero sera cambiado cuando se habilite el servico con el banco

    # Info pago
    ptm = ET.SubElement(cstmr,"PmtInf")

    #Aqui empieza los datos de la cuenta

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
    cd.text = "NURG"
    ctgypurp = ET.SubElement(pmt_tp_inf,"CtgyPurp")
    cd = ET.SubElement(ctgypurp,"Cd")
    cd.text = "SALA"


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
    
    #Colonia
    twn_nm = ET.SubElement(pstl_adr, "TwnNm")
    twn_nm.text = Colonia_Compañia

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
    bic.text = bic_banco #Nombre del banco

    pstl_adr_bank = ET.SubElement(fin_instn_id, "PstlAdr")
    bank_country = ET.SubElement(pstl_adr_bank, "Ctry")
    bank_country.text = "MX"
    #Aqui termina los datos de la cuenta

    for t in transferencias:

        cdt_trf_tx_inf = ET.SubElement(ptm, "CdtTrfTxInf")

        pmt_id = ET.SubElement(cdt_trf_tx_inf, "PmtId")

        # InstrId y EndToEndId: HSBC requiere la palabra "NOMINA" en ambos campos.
        # La funcion siguiente_referencia() ya genera el formato NOMINA{fecha}{seq}.
        # Si la referencia viene de otra fuente, se valida aqui antes de generar el XML.
        referencia_nomina = t["referencia"]
        if "NOMINA" not in str(referencia_nomina).upper():
            raise ValueError(
                f"ERROR Nomina — EndToEndId sin prefijo 'NOMINA':"
                f"\n   Beneficiario : '{t.get('beneficiario', '')}'"
                f"\n   Valor actual : '{referencia_nomina}'"
                f"\n   Problema     : HSBC requiere la palabra 'NOMINA' en InstrId y EndToEndId."
                f"\n   Ejemplo OK   : 'NOMINA20260908001'"
            )
        ET.SubElement(pmt_id, "InstrId").text = referencia_nomina   # Siempre debe contener la palabra NOMINA
        ET.SubElement(pmt_id, "EndToEndId").text = referencia_nomina  # Siempre debe contener la palabra NOMINA

        amt = ET.SubElement(cdt_trf_tx_inf, "Amt")

        #Monto a transferir
        instd_amt = ET.SubElement(amt, "InstdAmt")
        instd_amt.set("Ccy", "MXN")
        instd_amt.text = monto_xml(t["monto"]) # aqui se coloca el monto a transferir

        cdtr_agt = ET.SubElement(cdt_trf_tx_inf, "CdtrAgt")
        fin_instn_id2 = ET.SubElement(cdtr_agt, "FinInstnId")

        clr_sys = ET.SubElement(fin_instn_id2, "ClrSysMmbId")
        ET.SubElement(clr_sys, "MmbId").text = t["banco"] #Si unicamente se usara un solo banco reemplaze el dato por el numero del banco

        pstl_adr2 = ET.SubElement(fin_instn_id2, "PstlAdr")
        ET.SubElement(pstl_adr2, "Ctry").text = "MX"

        #Empiezan los datos al que se tranferira el dinero

        cdtr = ET.SubElement(cdt_trf_tx_inf, "Cdtr")
        ET.SubElement(cdtr, "Nm").text = t["beneficiario"]

        pstl_adr3 = ET.SubElement(cdtr, "PstlAdr")
        ET.SubElement(pstl_adr3, "StrtNm").text = t["calle"]
        ET.SubElement(pstl_adr3, "PstCd").text = t["cp"]
        ET.SubElement(pstl_adr3, "TwnNm").text = t["ciudad"]
        ET.SubElement(pstl_adr3, "Ctry").text = "MX"

        cdtr_acct = ET.SubElement(cdt_trf_tx_inf, "CdtrAcct")
        acct_id2 = ET.SubElement(cdtr_acct, "Id")
        othr2 = ET.SubElement(acct_id2, "Othr")

        ET.SubElement(othr2, "Id").text = t["cuenta"]  #cuenta a la que se transfiere, debe ser de 10 digitos para HSBC

        #Aqui terminan los datos de la persona a la que se transfiere

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
    Colonia_Compañia="Centro",              
    Ciudad_compañia="Los Mochis",           
    cuenta_ordenante="4043001353",          
    bic_banco="BIMEMXMM",                   
    referencia_unica=siguiente_referencia(), #Referencia unica identificacion facil en caso de auditorias

    transferencias = [
        {
            "referencia": siguiente_referencia(), #Referencia unica identificacion facil en caso de auditorias, no debe superar 16 caracteres
            "monto": 0.50, #Cantidad a depositar
            "beneficiario": "JUAN PEREZ", #Nombre de a quien se realiza el pago
            "cuenta": "4099999999", #Cuenta HSBC de 10 digitos
            "calle": "Calle Norte 45", #Domicilio
            "cp": "01000", #Codigo Postal
            "ciudad": "CDMX", #Ciudad en la que esta el domicilio
            "banco": "021" # Banco al que se realiza el pago o transferencia
        }
    ]
)