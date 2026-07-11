plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
}

android {
    namespace = "email.nimtz.nimtaflow.tv"
    compileSdk = 35

    defaultConfig {
        applicationId = "email.nimtz.nimtaflow.tv"
        minSdk = 23           // tv-foundation:1.0.0 requires API 23; FireTV Stick 4K = API 28
        targetSdk = 35
        versionCode = 24
        versionName = "1.23"
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }

    buildFeatures { compose = true }

    lint {
        disable += "NullSafeMutableLiveData"
    }
}

dependencies {
    val bom = platform(libs.compose.bom)
    implementation(bom)
    implementation(libs.compose.ui)
    implementation(libs.compose.material3)
    implementation(libs.compose.icons.extended)
    implementation(libs.compose.runtime)
    implementation(libs.compose.foundation)
    debugImplementation(libs.compose.ui.tooling)

    implementation(libs.tv.foundation)
    implementation(libs.tv.material)

    implementation(libs.nav.compose)
    implementation(libs.activity.compose)
    implementation(libs.lifecycle.runtime.ktx)
    implementation(libs.lifecycle.viewmodel.compose)
    implementation(libs.savedstate)
    implementation(libs.coil.compose)

    implementation(libs.media3.exoplayer)
    implementation(libs.media3.ui)
    implementation(libs.media3.session)

    implementation(libs.okhttp)
    implementation(libs.okhttp.logging)

    implementation(libs.datastore.prefs)
    implementation(libs.coroutines.android)
    implementation(libs.serialization.json)
    implementation(libs.zxing.core)
}
