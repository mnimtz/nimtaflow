package email.nimtz.nimtaflow.tv.util

private val MONTHS_SHORT = listOf("", "Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez")
private val MONTHS_LONG  = listOf("", "Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember")

/** "2023-07-15T..." → "15. Jul 2023" */
fun formatDate(isoDate: String?): String {
    if (isoDate == null || isoDate.length < 10) return ""
    val parts = isoDate.substring(0, 10).split("-")
    if (parts.size < 3) return isoDate.substring(0, 10)
    val m = parts[1].toIntOrNull() ?: return isoDate.substring(0, 10)
    return "${parts[2].trimStart('0')}. ${MONTHS_SHORT.getOrElse(m) { parts[1] }} ${parts[0]}"
}

/** "2023-07-15T..." → "Juli 2023" */
fun formatMonthYear(isoDate: String?): String {
    if (isoDate == null || isoDate.length < 7) return "Unbekannt"
    val parts = isoDate.substring(0, 7).split("-")
    if (parts.size < 2) return "Unbekannt"
    val m = parts[1].toIntOrNull() ?: return "Unbekannt"
    return "${MONTHS_LONG.getOrElse(m) { parts[1] }} ${parts[0]}"
}

/** "2023-07-15T..." → "2023-07" (for grouping) */
fun monthKey(isoDate: String?): String =
    if (isoDate != null && isoDate.length >= 7) isoDate.substring(0, 7) else "0000-00"
