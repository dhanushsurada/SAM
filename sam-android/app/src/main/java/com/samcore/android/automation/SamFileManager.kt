package com.samcore.android.automation

import android.content.Context
import android.os.Environment
import android.util.Log
import java.io.File
import java.io.FileInputStream
import java.io.FileOutputStream
import java.security.MessageDigest

/**
 * Handles scoped storage and received file operations.
 * Complies with Android 11+ scoped storage requirements (no broad MANAGE_EXTERNAL_STORAGE).
 */
class SamFileManager(private val context: Context) {

    private val downloadsDir: File
        get() = context.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS) ?: context.filesDir

    fun saveReceivedFile(filename: String, bytes: ByteArray, expectedSha256: String? = null): FileResult {
        return try {
            val sanitized = filename.replace("[^a-zA-Z0-9._-]".toRegex(), "_")
            val targetFile = File(downloadsDir, sanitized)

            FileOutputStream(targetFile).use { it.write(bytes) }

            val actualSha256 = computeSha256(targetFile)
            if (expectedSha256 != null && !actualSha256.equals(expectedSha256, ignoreCase = true)) {
                targetFile.delete()
                return FileResult(
                    success = false,
                    error = "Checksum mismatch: expected $expectedSha256, got $actualSha256"
                )
            }

            Log.i(TAG, "Saved file ${targetFile.name} (${bytes.size} bytes) to ${targetFile.absolutePath}")
            FileResult(
                success = true,
                filePath = targetFile.absolutePath,
                fileSize = bytes.size.toLong(),
                sha256 = actualSha256
            )
        } catch (e: Exception) {
            Log.e(TAG, "Failed to save file: ${e.message}")
            FileResult(success = false, error = e.message)
        }
    }

    fun readFileBytes(filename: String): ByteArray? {
        val target = File(downloadsDir, filename)
        if (!target.exists() || !target.isFile) return null
        return target.readBytes()
    }

    fun listReceivedFiles(): List<FileInfo> {
        val files = downloadsDir.listFiles() ?: return emptyList()
        return files.filter { it.isFile }.map {
            FileInfo(
                name = it.name,
                path = it.absolutePath,
                sizeBytes = it.length(),
                lastModified = it.lastModified()
            )
        }
    }

    private fun computeSha256(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        FileInputStream(file).use { fis ->
            val buffer = ByteArray(8192)
            var read: Int
            while (fis.read(buffer).also { read = it } != -1) {
                digest.update(buffer, 0, read)
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }

    companion object {
        private const val TAG = "SamFileManager"
    }
}

data class FileResult(
    val success: Boolean,
    val filePath: String? = null,
    val fileSize: Long = 0,
    val sha256: String? = null,
    val error: String? = null
)

data class FileInfo(
    val name: String,
    val path: String,
    val sizeBytes: Long,
    val lastModified: Long
)
