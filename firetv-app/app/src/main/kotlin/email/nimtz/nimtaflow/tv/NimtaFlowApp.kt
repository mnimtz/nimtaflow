package email.nimtz.nimtaflow.tv

import android.app.Application
import email.nimtz.nimtaflow.tv.api.APIClient
import email.nimtz.nimtaflow.tv.util.Prefs

class NimtaFlowApp : Application() {
    lateinit var api: APIClient
    lateinit var prefs: Prefs

    override fun onCreate() {
        super.onCreate()
        prefs = Prefs(this)
        api = APIClient("")   // URL set once server setup completes
    }
}
