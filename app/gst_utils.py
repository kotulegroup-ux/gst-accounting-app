"""
GST Utilities: State codes, Indian currency number-to-words, and GST tax calculations.
"""

GST_STATE_CODES = {
    "01": "Jammu & Kashmir",
    "02": "Himachal Pradesh",
    "03": "Punjab",
    "04": "Chandigarh",
    "05": "Uttarakhand",
    "06": "Haryana",
    "07": "Delhi",
    "08": "Rajasthan",
    "09": "Uttar Pradesh",
    "10": "Bihar",
    "11": "Sikkim",
    "12": "Arunachal Pradesh",
    "13": "Nagaland",
    "14": "Manipur",
    "15": "Mizoram",
    "16": "Tripura",
    "17": "Meghalaya",
    "18": "Assam",
    "19": "West Bengal",
    "20": "Jharkhand",
    "21": "Odisha",
    "22": "Chhattisgarh",
    "23": "Madhya Pradesh",
    "24": "Gujarat",
    "26": "Dadra & Nagar Haveli and Daman & Diu",
    "27": "Maharashtra",
    "28": "Andhra Pradesh (Old)",
    "29": "Karnataka",
    "30": "Goa",
    "31": "Lakshadweep",
    "32": "Kerala",
    "33": "Tamil Nadu",
    "34": "Puducherry",
    "35": "Andaman & Nicobar Islands",
    "36": "Telangana",
    "37": "Andhra Pradesh (New)",
    "38": "Ladakh",
    "97": "Other Territory"
}

def get_state_info_from_gstin(gstin: str):
    """Extract 2-digit state code and state name from GSTIN."""
    if not gstin or len(gstin.strip()) < 2:
        return "", ""
    code = gstin.strip()[:2]
    name = GST_STATE_CODES.get(code, "Unknown")
    return code, name

def is_interstate(supplier_state_code: str, buyer_state_code: str) -> bool:
    """Check if supply is inter-state (IGST) or intra-state (CGST + SGST)."""
    s = (supplier_state_code or "").strip()
    b = (buyer_state_code or "").strip()
    if not s or not b:
        return False
    return s != b

def calculate_item_taxes(taxable_value: float, gst_rate: float, is_interstate_flag: bool):
    """
    Computes tax amounts based on taxable value, gst rate (%), and whether interstate or intra-state.
    """
    taxable_value = round(float(taxable_value or 0), 2)
    gst_rate = float(gst_rate or 0)
    
    total_tax = round((taxable_value * gst_rate) / 100.0, 2)
    
    if is_interstate_flag:
        cgst_rate = 0.0
        cgst_amount = 0.0
        sgst_rate = 0.0
        sgst_amount = 0.0
        igst_rate = gst_rate
        igst_amount = total_tax
    else:
        cgst_rate = round(gst_rate / 2.0, 2)
        cgst_amount = round(total_tax / 2.0, 2)
        sgst_rate = round(gst_rate / 2.0, 2)
        # Handle 1 paisa rounding disparity if any
        sgst_amount = round(total_tax - cgst_amount, 2)
        igst_rate = 0.0
        igst_amount = 0.0

    total_amount = round(taxable_value + total_tax, 2)
    return {
        "taxable_value": taxable_value,
        "gst_rate": gst_rate,
        "cgst_rate": cgst_rate,
        "cgst_amount": cgst_amount,
        "sgst_rate": sgst_rate,
        "sgst_amount": sgst_amount,
        "igst_rate": igst_rate,
        "igst_amount": igst_amount,
        "total_tax": total_tax,
        "total_amount": total_amount
    }

def amount_to_words_indian(num: float) -> str:
    """Convert amount to Indian English words (Rupees and Paise)."""
    try:
        num = round(float(num), 2)
    except (ValueError, TypeError):
        return "Zero Rupees Only"

    if num == 0:
        return "Zero Rupees Only"

    units = [
        "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
        "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
        "Seventeen", "Eighteen", "Nineteen"
    ]
    tens = [
        "", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"
    ]

    def two_digits(n: int) -> str:
        if n < 20:
            return units[n]
        d1 = n // 10
        d2 = n % 10
        return (tens[d1] + (" " + units[d2] if d2 > 0 else "")).strip()

    def three_digits(n: int) -> str:
        hundred = n // 100
        rem = n % 100
        res = ""
        if hundred > 0:
            res += units[hundred] + " Hundred"
            if rem > 0:
                res += " and "
        if rem > 0:
            res += two_digits(rem)
        return res

    rupees = int(num)
    paise = int(round((num - rupees) * 100))

    crore = rupees // 10000000
    rupees %= 10000000

    lakh = rupees // 100000
    rupees %= 100000

    thousand = rupees // 1000
    rupees %= 1000

    rem_rupees = rupees

    parts = []
    if crore > 0:
        parts.append(two_digits(crore) + " Crore")
    if lakh > 0:
        parts.append(two_digits(lakh) + " Lakh")
    if thousand > 0:
        parts.append(two_digits(thousand) + " Thousand")
    if rem_rupees > 0:
        parts.append(three_digits(rem_rupees))

    rupees_str = " ".join(parts).strip()
    if not rupees_str:
        rupees_str = "Zero"

    result = f"{rupees_str} Rupees"
    if paise > 0:
        paise_str = two_digits(paise)
        result += f" and {paise_str} Paise"

    result += " Only"
    return result
