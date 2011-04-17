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

public class ImportIncomingCommand {

    private final int BATCH_SIZE = 20;

    public void run() {
/*        Iterable<IncomingFingerprint> incomingFingerprints = fingerprintData.findIncoming(BATCH_SIZE);
        for (IncomingFingerprint fp : incomingFingerprints) {
            Iterable<Result> results = fingerprintData.search(fp.getFingerprint(), fp.getLength());
        }*/
    }

}
