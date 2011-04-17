// Acoustid -- Audio fingerprint lookup server
// Copyright (C) 2010  Lukas Lalinsky
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with this program.  If not, see <http://www.gnu.org/licenses/>.

package org.acoustid;

import java.io.IOException;
import org.acoustid.util.FingerprintCompressor;
import org.acoustid.util.FingerprintDecompressor;
import org.acoustid.util.IncompatibleFingerprintVersion;
import org.apache.commons.codec.binary.Base64;

public class FingerprintUtils {

    public static int[] decodeFingerprint(String str, int expectedVersion) throws IllegalArgumentException, IncompatibleFingerprintVersion {
        try {
            return FingerprintDecompressor.decompress(Base64.decodeBase64(str), expectedVersion);
        }
        catch (IOException ex) {
            throw new IllegalArgumentException("Invalid fingerprint", ex);
        }
    }
    
    public static String encodeFingerprint(int[] fp, int version) throws IllegalArgumentException {
        try {
            return new String(Base64.encodeBase64(FingerprintCompressor.compress(fp, version), false, true), "ASCII");
        }
        catch (IOException ex) {
            throw new IllegalArgumentException("Invalid fingerprint", ex);
        }
    }

    public static String encodeFingerprint(int[] fp) throws IllegalArgumentException {
        return encodeFingerprint(fp, 0);
    }

}
