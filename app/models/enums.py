import enum


class ServiceTypeEnum(str, enum.Enum):
    AIRTIME = "airtime"
    DATA = "data"
    ELECTRICITY = "electricity"
    CABLE = "cable"
    EXAM_PINS = "exam_pins"
    EDUCATION = "education"
    BETTING = "betting"


class TxnStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCESSFUL = "successful"
    FAILED = "failed"


class Network(str, enum.Enum):
    MTN = "MTN"
    AIRTEL = "AIRTEL"
    GLO = "GLO"
    NINE_MOBILE = "9MOBILE"

    @property
    def label(self) -> str:
        return {"MTN": "MTN", "AIRTEL": "Airtel", "GLO": "Glo", "9MOBILE": "9mobile"}[self.value]


class MeterType(str, enum.Enum):
    PREPAID = "prepaid"
    POSTPAID = "postpaid"
