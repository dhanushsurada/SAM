package com.samcore.android.automation

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File
import java.nio.charset.StandardCharsets

class SamFileManagerTest {

    @get:Rule
    val tempFolder = TemporaryFolder()

    @Test
    fun computeSha256_knownInput_matchesExpectedHash() {
        val manager = SamFileManager(context = null, baseDir = tempFolder.root)
        // SHA-256 for "hello world"
        val expected = "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
        val actual = manager.computeSha256("hello world".toByteArray(StandardCharsets.UTF_8))
        assertEquals(expected, actual)
    }

    @Test
    fun saveReceivedFile_matchingChecksum_writesFileAndReturnsSuccess() {
        val isolatedDir = tempFolder.newFolder("downloads_success")
        val manager = SamFileManager(context = null, baseDir = isolatedDir)
        val data = "Authentic test payload content for cross-device file transfer".toByteArray(StandardCharsets.UTF_8)
        val expectedHash = manager.computeSha256(data)

        val result = manager.saveReceivedFile(
            filename = "sample_test_doc.txt",
            bytes = data,
            expectedSha256 = expectedHash
        )

        assertTrue(result.success)
        assertNull(result.error)
        assertEquals(data.size.toLong(), result.fileSize)
        assertEquals(expectedHash, result.sha256)
        assertNotNull(result.filePath)

        val savedFile = File(result.filePath!!)
        assertTrue(savedFile.exists())
        assertEquals(String(data, StandardCharsets.UTF_8), savedFile.readText(StandardCharsets.UTF_8))
    }

    @Test
    fun saveReceivedFile_corruptedChecksum_deletesFileAndReturnsFailure() {
        val isolatedDir = tempFolder.newFolder("downloads_corrupt")
        val manager = SamFileManager(context = null, baseDir = isolatedDir)
        val data = "Uncorrupted data".toByteArray(StandardCharsets.UTF_8)
        val wrongHash = "0000000000000000000000000000000000000000000000000000000000000000"

        val result = manager.saveReceivedFile(
            filename = "tampered_file.txt",
            bytes = data,
            expectedSha256 = wrongHash
        )

        assertFalse(result.success)
        assertNotNull(result.error)
        assertTrue(result.error!!.contains("Checksum mismatch"))

        // Verify the file was deleted from disk due to corruption
        val targetPath = File(isolatedDir, "tampered_file.txt")
        assertFalse(targetPath.exists())
    }

    @Test
    fun readFileBytes_and_listReceivedFiles_succeeds() {
        val isolatedDir = tempFolder.newFolder("downloads_roundtrip")
        val manager = SamFileManager(context = null, baseDir = isolatedDir)
        val data = "Content to read back".toByteArray(StandardCharsets.UTF_8)
        val result = manager.saveReceivedFile("roundtrip.bin", data)
        assertTrue(result.success)

        val readBack = manager.readFileBytes("roundtrip.bin")
        assertNotNull(readBack)
        assertEquals(String(data, StandardCharsets.UTF_8), String(readBack!!, StandardCharsets.UTF_8))

        val list = manager.listReceivedFiles()
        assertTrue(list.any { it.name == "roundtrip.bin" })
    }
}
