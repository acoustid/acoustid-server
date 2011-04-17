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

import java.io.ByteArrayInputStream;
import java.io.DataInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;

/**
 * Decompressor for integer fingerprints, based on the PFOR-DELTA compression
 * algorithm.
 */
public class FingerprintDecompressor {

    private InputStream input;
    private DataInputStream dataInput;
    private int[] data;
    private ArrayList<Integer> bits = new ArrayList<Integer>();

    private static final int MAX_NORMAL_VALUE = FingerprintCompressor.MAX_NORMAL_VALUE;
    private static final int NORMAL_BITS = FingerprintCompressor.NORMAL_BITS;
    private static final int EXCEPTION_BITS = FingerprintCompressor.EXCEPTION_BITS;
    
    public FingerprintDecompressor(InputStream inp) {
        input = inp;
        dataInput = new DataInputStream(input);
    }

    private void readNormalBits() throws IOException {
        BitStreamReader reader = new BitStreamReader(dataInput);
        int i = 0;
        while (i < data.length) {
            int bit = reader.read(NORMAL_BITS);
            if (bit == 0) {
                i++;
            }
            bits.add(bit);
        }
    }

    private void unpackBits() throws IOException {
        int i = 0, lastBit = 0, value = 0;
        for (int bit : bits) {
            if (bit == 0) {
                data[i] = (i > 0) ? value ^ data[i - 1] : value;
                value = 0;
                lastBit = 0;
                i++;
                continue;
            }
            bit += lastBit;
            lastBit = bit;
            value |= 1 << (bit - 1);
        }
    }

    private void readExceptionBits() throws IOException {
        BitStreamReader reader = new BitStreamReader(dataInput);
        for (int i = 0; i < bits.size(); i++) {
            if (bits.get(i) == MAX_NORMAL_VALUE) {
                bits.set(i, bits.get(i) + reader.read(EXCEPTION_BITS));
            }
        }
    }

    public int[] decompress(int expectedVersion) throws IOException, IncompatibleFingerprintVersion {
        int length = dataInput.readInt();
        int version = (length >> 24) & 0xFF;
        if (version != expectedVersion)
            throw new IncompatibleFingerprintVersion("Expected fingerprint version " + expectedVersion + ", got " + version + ".");
        length = length & 0x00FFFFFF;
        data = new int[length];
        for (int i = 0; i < length; i++) {
            data[i] = -1;
        }
        readNormalBits();
        readExceptionBits();
        unpackBits();
        return data;
    }

    public static int[] decompress(byte[] data) throws IOException, IncompatibleFingerprintVersion {
        return decompress(data, 0);
    }

    public static int[] decompress(byte[] data, int expectedVersion) throws IOException, IncompatibleFingerprintVersion {
        FingerprintDecompressor decompressor = new FingerprintDecompressor(new ByteArrayInputStream(data));
        return decompressor.decompress(expectedVersion);
    }

}
