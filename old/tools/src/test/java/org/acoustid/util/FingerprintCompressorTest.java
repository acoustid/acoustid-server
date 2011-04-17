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

package org.acoustid.util;

import java.io.IOException;
import junit.framework.TestCase;
import org.apache.commons.lang.ArrayUtils;

public class FingerprintCompressorTest extends TestCase {
    
    public FingerprintCompressorTest(String testName) {
        super(testName);
    }

    public void testOneItemOneBit() throws IOException {
        int[] fingerprint = { 1 };
        byte[] expected = { 0, 0, 0, 1, 1 };
        assertEquals(ArrayUtils.toString(expected), ArrayUtils.toString(FingerprintCompressor.compress(fingerprint)));
    }

    public void testOneItemThreeBits() throws IOException {
        int[] fingerprint = { 7 };
        byte[] expected = { 0, 0, 0, 1, 73, 0 };
        assertEquals(ArrayUtils.toString(expected), ArrayUtils.toString(FingerprintCompressor.compress(fingerprint)));
    }

    public void testOneItemOneBitExcept() throws IOException {
        int[] fingerprint = { 1<<6 };
        byte[] expected = { 0, 0, 0, 1, 7, 0 };
        assertEquals(ArrayUtils.toString(expected), ArrayUtils.toString(FingerprintCompressor.compress(fingerprint)));
    }

    public void testOneItemOneBitExcept2() throws IOException {
        int[] fingerprint = { 1<<8 };
        byte[] expected = { 0, 0, 0, 1, 7, 2 };
        assertEquals(ArrayUtils.toString(expected), ArrayUtils.toString(FingerprintCompressor.compress(fingerprint)));
    }

    public void testTwoItems() throws IOException {
        int[] fingerprint = { 1, 0 };
        byte[] expected = { 0, 0, 0, 2, 65, 0 };
        assertEquals(ArrayUtils.toString(expected), ArrayUtils.toString(FingerprintCompressor.compress(fingerprint)));
    }

    public void testTwoItemsNoChange() throws IOException {
        int[] fingerprint = { 1, 1 };
        byte[] expected = { 0, 0, 0, 2, 1, 0 };
        assertEquals(ArrayUtils.toString(expected), ArrayUtils.toString(FingerprintCompressor.compress(fingerprint)));
    }

}
