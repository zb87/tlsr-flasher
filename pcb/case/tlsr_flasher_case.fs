// Parametric 3D-printable Snap-Fit Enclosure for tlsr-flasher (47.00 x 26.00 mm PCB)
//
// Features:
//   - Slim two-piece snap-fit enclosure with stepped lap rim + 45-deg zero-support detent latches
//   - Two tall internal M2 alignment pins (TL @ (2.8, 23.2), BR @ (44.2, 2.8) mm) engaging top lid sockets
//   - Support rails clear of H1/H2 bottom through-hole solder pins (1.4 mm protrusion) and USB1 tabs (6 mm)
//   - West USB-C opening with stepped cable-boot recess so standard plugs seat fully
//   - Closed South wall (no SW1 cutout/button)
//   - Top cutout for H1 1x5P target header (GND, PWR, 3V3, SWM, RST); H2 self-prog header enclosed cleanly
//   - 1.2 mm indicator pinholes over LED1 (5V) and LED2 (PWR)
//   - Debossed top labels (prints face-down with zero supports)
//   - Optional "Print Layout" toggle that flips the Top Lid face-down on Z=0 beside the Bottom Shell

annotation { "Feature Type Name" : "TLSR Flasher Case" }
export const tlsrFlasherCase = defineFeature(function(context is Context, id is Id, definition is map)
    precondition
    {
        annotation { "Name" : "PCB XY Clearance" }
        isLength(definition.pcbClearance, { (millimeter) : [0.1, 0.25, 0.8] } as LengthBoundSpec);

        annotation { "Name" : "Snap Rim Clearance" }
        isLength(definition.snapClearance, { (millimeter) : [0.05, 0.10, 0.4] } as LengthBoundSpec);

        annotation { "Name" : "Wall Thickness" }
        isLength(definition.wall, { (millimeter) : [1.4, 1.6, 3.0] } as LengthBoundSpec);

        annotation { "Name" : "Bottom Floor Thickness" }
        isLength(definition.floorThk, { (millimeter) : [0.8, 1.4, 3.0] } as LengthBoundSpec);

        annotation { "Name" : "Top Roof Thickness" }
        isLength(definition.roofThk, { (millimeter) : [0.8, 1.4, 3.0] } as LengthBoundSpec);

        annotation { "Name" : "Bottom Pin Clearance" }
        isLength(definition.botClear, { (millimeter) : [1.5, 2.0, 4.0] } as LengthBoundSpec);

        annotation { "Name" : "Top Component Clearance" }
        isLength(definition.topClear, { (millimeter) : [3.2, 3.4, 9.2] } as LengthBoundSpec);

        annotation { "Name" : "LED Pinhole Dia" }
        isLength(definition.ledHoleDia, { (millimeter) : [0.6, 1.2, 3.5] } as LengthBoundSpec);

        annotation { "Name" : "Debossed Top Labels" }
        definition.addLabels is boolean;

        annotation { "Name" : "Print Layout (Side-by-Side)" }
        definition.printLayout is boolean;
    }
    {
        // Fixed PCB geometry (mm) - origin centered around 47.00 x 26.00 mm PCB
        const pcbLen = 47.0 * millimeter;
        const pcbWid = 26.0 * millimeter;
        const pcbThk = 1.6 * millimeter;
        const pcbR   = 1.8 * millimeter;
        const halfPcbX = pcbLen / 2; // 23.5 mm
        const halfPcbY = pcbWid / 2; // 13.0 mm

        // Helpers converting PCB coordinates (0..47, 0..26) to centered XY
        const px = function(x_mm is number) { return x_mm * millimeter - halfPcbX; };
        const py = function(y_mm is number) { return y_mm * millimeter - halfPcbY; };

        const clr = definition.pcbClearance;
        const wall = definition.wall;
        const halfWall = wall / 2;

        const inHalfX  = halfPcbX + clr;
        const inHalfY  = halfPcbY + clr;
        const outHalfX = inHalfX + wall;
        const outHalfY = inHalfY + wall;
        const outR     = pcbR + clr + wall;
        const inR      = pcbR + clr;
        const midHalfX = inHalfX + halfWall;
        const midHalfY = inHalfY + halfWall;
        const midR     = inR + halfWall;

        // Z-levels relative to PCB top surface = 0
        const botPcbZ    = -pcbThk;                       // -1.60 mm
        const botCavZ    = botPcbZ - definition.botClear; // -3.60 mm
        const botExtZ    = botCavZ - definition.floorThk; // -5.00 mm
        const topCavZ    = definition.topClear;           // +3.40 mm
        const topExtZ    = topCavZ + definition.roofThk;  // +4.80 mm
        const seamZ      = topCavZ;                       // +3.40 mm (clean parting plane)
        const lapH       = 1.6 * millimeter;
        const stepZ      = seamZ - lapH;                  // +1.80 mm

        // =========================================================================
        // 1. BOTTOM SHELL (Z = botExtZ .. seamZ)
        // =========================================================================
        // 1a. Outer solid block -> fillet vertical corners -> shell open at top (+Z)
        fCuboid(context, id + "botOuter", {
            "corner1" : vector(-outHalfX, -outHalfY, botExtZ),
            "corner2" : vector(outHalfX, outHalfY, seamZ)
        });
        var botBody = qCreatedBy(id + "botOuter", EntityType.BODY);
        opFillet(context, id + "botFillet", {
            "entities" : qEdgeTopologyFilter(qParallelEdges(qOwnedByBody(botBody, EntityType.EDGE), Z_DIRECTION), EdgeTopology.TWO_SIDED),
            "radius" : outR
        });

        // Hollow out interior cavity down to botCavZ
        const skCav = newSketchOnPlane(context, id + "skCav", {
            "sketchPlane" : plane(vector(0 * millimeter, 0 * millimeter, botCavZ), Z_DIRECTION, X_DIRECTION)
        });
        skRectangle(skCav, "r", {
            "firstCorner" : vector(-inHalfX, -inHalfY),
            "secondCorner" : vector(inHalfX, inHalfY)
        });
        skSolve(skCav);
        opExtrude(context, id + "extCav", {
            "entities" : qSketchRegion(id + "skCav"),
            "direction" : Z_DIRECTION,
            "endBound" : BoundingType.BLIND,
            "endDepth" : seamZ - botCavZ + 0.5 * millimeter
        });
        opDeleteBodies(context, id + "delSkCav", { "entities" : qCreatedBy(id + "skCav", EntityType.BODY) });
        opFillet(context, id + "cavFillet", {
            "entities" : qEdgeTopologyFilter(qParallelEdges(qOwnedByBody(qCreatedBy(id + "extCav", EntityType.BODY), EntityType.EDGE), Z_DIRECTION), EdgeTopology.TWO_SIDED),
            "radius" : inR
        });
        opBoolean(context, id + "subCav", {
            "tools" : qCreatedBy(id + "extCav", EntityType.BODY),
            "targets" : botBody,
            "operationType" : BooleanOperationType.SUBTRACTION
        });

        // 1b. Cut upper-wall step (stepZ .. seamZ) to leave thin outer lap rim (wall - halfWall)
        const skStep = newSketchOnPlane(context, id + "skStep", {
            "sketchPlane" : plane(vector(0 * millimeter, 0 * millimeter, stepZ), Z_DIRECTION, X_DIRECTION)
        });
        skRectangle(skStep, "r", {
            "firstCorner" : vector(-midHalfX, -midHalfY),
            "secondCorner" : vector(midHalfX, midHalfY)
        });
        skSolve(skStep);
        opExtrude(context, id + "extStep", {
            "entities" : qSketchRegion(id + "skStep"),
            "direction" : Z_DIRECTION,
            "endBound" : BoundingType.BLIND,
            "endDepth" : lapH + 0.5 * millimeter
        });
        opDeleteBodies(context, id + "delSkStep", { "entities" : qCreatedBy(id + "skStep", EntityType.BODY) });
        opFillet(context, id + "stepFillet", {
            "entities" : qEdgeTopologyFilter(qParallelEdges(qOwnedByBody(qCreatedBy(id + "extStep", EntityType.BODY), EntityType.EDGE), Z_DIRECTION), EdgeTopology.TWO_SIDED),
            "radius" : midR
        });
        opBoolean(context, id + "subStep", {
            "tools" : qCreatedBy(id + "extStep", EntityType.BODY),
            "targets" : botBody,
            "operationType" : BooleanOperationType.SUBTRACTION
        });

        // 1c. USB-C cutout on West wall (USB1 Y = 9.04..17.98 -> centered ~13.51, Z = 0.07..3.09)
        //     Inner opening: 9.8 x 3.65 mm (Y = 8.61..18.41, Z = -0.25..seamZ)
        //     Outer boot recess: 12.8 x 4.0 mm inside Bottom Shell only (Z = -0.60..seamZ) so Top Lid stays flush
        fCuboid(context, id + "usbCutIn", {
            "corner1" : vector(-outHalfX - 1 * millimeter, py(8.61), -0.25 * millimeter),
            "corner2" : vector(-inHalfX + 0.8 * millimeter, py(18.41), seamZ + 0.5 * millimeter)
        });
        fCuboid(context, id + "usbCutBoot", {
            "corner1" : vector(-outHalfX - 1 * millimeter, py(7.11), -0.60 * millimeter),
            "corner2" : vector(-outHalfX + 0.80 * millimeter, py(19.91), seamZ + 0.5 * millimeter)
        });
        opBoolean(context, id + "subUsb", {
            "tools" : qUnion([qCreatedBy(id + "usbCutIn", EntityType.BODY), qCreatedBy(id + "usbCutBoot", EntityType.BODY)]),
            "targets" : botBody,
            "operationType" : BooleanOperationType.SUBTRACTION
        });

        // 1d. Internal M2 Alignment Standoffs + Tall Pins engaging Top Lid Sockets (avoiding H1/H2 TH pin zones)
        const standoffs = [
            { "x" : px(2.80),  "y" : py(23.20), "tag" : "TL" },
            { "x" : px(44.20), "y" : py(2.80),  "tag" : "BR" }
        ];
        var supportTools = [botBody];
        for (var i = 0; i < size(standoffs); i += 1)
        {
            const s = standoffs[i];
            fCylinder(context, id + ("boss" ~ i), {
                "bottomCenter" : vector(s.x, s.y, botCavZ - 0.1 * millimeter),
                "topCenter" : vector(s.x, s.y, botPcbZ),
                "radius" : 1.9 * millimeter
            });
            fCylinder(context, id + ("pin" ~ i), {
                "bottomCenter" : vector(s.x, s.y, botPcbZ - 0.1 * millimeter),
                "topCenter" : vector(s.x, s.y, topCavZ - 0.55 * millimeter),
                "radius" : 0.95 * millimeter
            });
            // Chamfer pin tip for smooth insertion into Top Lid sockets
            opChamfer(context, id + ("pinCh" ~ i), {
                "entities" : qFarthestAlong(qOwnedByBody(qCreatedBy(id + ("pin" ~ i), EntityType.BODY), EntityType.EDGE), Z_DIRECTION),
                "chamferType" : ChamferType.EQUAL_OFFSETS,
                "width" : 0.25 * millimeter
            });
            supportTools = append(supportTools, qCreatedBy(id + ("boss" ~ i), EntityType.BODY));
            supportTools = append(supportTools, qCreatedBy(id + ("pin" ~ i), EntityType.BODY));
        }

        // Extra bottom PCB support ledges in pin-free corners (under USB1/BL and North-Center)
        fCuboid(context, id + "ledgeBL", {
            "corner1" : vector(-inHalfX - 0.1 * millimeter, -inHalfY - 0.1 * millimeter, botCavZ - 0.1 * millimeter),
            "corner2" : vector(px(10.0), py(1.2), botPcbZ)
        });
        fCuboid(context, id + "ledgeN", {
            "corner1" : vector(px(8.0), py(25.0), botCavZ - 0.1 * millimeter),
            "corner2" : vector(px(39.0), inHalfY + 0.1 * millimeter, botPcbZ)
        });
        fCuboid(context, id + "ledgeUSB", {
            "corner1" : vector(-inHalfX - 0.1 * millimeter, py(10.51), botCavZ - 0.1 * millimeter),
            "corner2" : vector(px(3.0), py(16.51), botPcbZ)
        });
        supportTools = append(supportTools, qCreatedBy(id + "ledgeBL", EntityType.BODY));
        supportTools = append(supportTools, qCreatedBy(id + "ledgeN", EntityType.BODY));
        supportTools = append(supportTools, qCreatedBy(id + "ledgeUSB", EntityType.BODY));

        opBoolean(context, id + "unionSupports", {
            "tools" : qUnion(supportTools),
            "operationType" : BooleanOperationType.UNION
        });
        botBody = qCreatedBy(id + "botOuter", EntityType.BODY);

        // 1f. Cut 4x 45-deg Snap-Fit V-Grooves into Bottom Shell inner rim (North & South)
        const snapSpans = [
            { "x1" : px(12.0), "x2" : px(19.0), "y" :  midHalfY, "sign" :  1 },
            { "x1" : px(30.5), "x2" : px(37.5), "y" :  midHalfY, "sign" :  1 },
            { "x1" : px(15.0), "x2" : px(22.0), "y" : -midHalfY, "sign" : -1 },
            { "x1" : px(30.5), "x2" : px(37.5), "y" : -midHalfY, "sign" : -1 }
        ];
        const grooveZ = stepZ + lapH * 0.52;
        var grooveTools = [];
        for (var i = 0; i < size(snapSpans); i += 1)
        {
            const sp = snapSpans[i];
            const skG = newSketchOnPlane(context, id + ("skG" ~ i), {
                "sketchPlane" : plane(vector(sp.x1, 0 * millimeter, 0 * millimeter), X_DIRECTION, Y_DIRECTION)
            });
            const yBase = sp.y - sp.sign * 0.15 * millimeter;
            const yTip  = sp.y + sp.sign * 0.32 * millimeter;
            skPolyline(skG, "g", {
                "points" : [
                    vector(yBase, grooveZ - 0.48 * millimeter),
                    vector(yTip,  grooveZ),
                    vector(yBase, grooveZ + 0.48 * millimeter),
                    vector(yBase, grooveZ - 0.48 * millimeter)
                ]
            });
            skSolve(skG);
            opExtrude(context, id + ("extG" ~ i), {
                "entities" : qSketchRegion(id + ("skG" ~ i)),
                "direction" : X_DIRECTION,
                "endBound" : BoundingType.BLIND,
                "endDepth" : sp.x2 - sp.x1
            });
            opDeleteBodies(context, id + ("delSkG" ~ i), { "entities" : qCreatedBy(id + ("skG" ~ i), EntityType.BODY) });
            grooveTools = append(grooveTools, qCreatedBy(id + ("extG" ~ i), EntityType.BODY));
        }
        opBoolean(context, id + "subGrooves", {
            "tools" : qUnion(grooveTools),
            "targets" : botBody,
            "operationType" : BooleanOperationType.SUBTRACTION
        });

        // =========================================================================
        // 2. TOP LID (Z = seamZ .. topExtZ, plus inner snap skirt down to stepZ + 0.15)
        // =========================================================================
        fCuboid(context, id + "topPlate", {
            "corner1" : vector(-outHalfX, -outHalfY, seamZ),
            "corner2" : vector(outHalfX, outHalfY, topExtZ)
        });
        var topBody = qCreatedBy(id + "topPlate", EntityType.BODY);
        opFillet(context, id + "topFillet", {
            "entities" : qEdgeTopologyFilter(qParallelEdges(qOwnedByBody(topBody, EntityType.EDGE), Z_DIRECTION), EdgeTopology.TWO_SIDED),
            "radius" : outR
        });

        // Chamfer/soften top outer perimeter edge (0.45 mm aesthetic bevel)
        const topUpperFace = qFarthestAlong(qParallelPlanes(qOwnedByBody(topBody, EntityType.FACE), XY_PLANE), Z_DIRECTION);
        opChamfer(context, id + "topBevel", {
            "entities" : qAdjacent(topUpperFace, AdjacencyType.EDGE, EntityType.EDGE),
            "chamferType" : ChamferType.EQUAL_OFFSETS,
            "width" : 0.45 * millimeter
        });

        // 2a. Inner Skirt Ring (sits between inHalf and midHalf - snapClearance, from stepZ+0.15 to seamZ)
        //     Built via outer-fillet minus inner-fillet so wall thickness stays uniform around all 4 corners,
        //     and trimmed ONLY at USB1, SW1, and H1 openings so West & East skirt segments prevent X-axis wiggle.
        const skirtBotZ = stepZ + 0.15 * millimeter;
        const skirtOutX = midHalfX - definition.snapClearance;
        const skirtOutY = midHalfY - definition.snapClearance;
        const skirtOutR = midR - definition.snapClearance;

        fCuboid(context, id + "skOutBox", {
            "corner1" : vector(-skirtOutX, -skirtOutY, skirtBotZ),
            "corner2" : vector(skirtOutX, skirtOutY, seamZ + 0.2 * millimeter)
        });
        var skirtBody = qCreatedBy(id + "skOutBox", EntityType.BODY);
        opFillet(context, id + "skirtOutFillet", {
            "entities" : qEdgeTopologyFilter(qParallelEdges(qOwnedByBody(skirtBody, EntityType.EDGE), Z_DIRECTION), EdgeTopology.TWO_SIDED),
            "radius" : skirtOutR
        });
        fCuboid(context, id + "skInBox", {
            "corner1" : vector(-inHalfX, -inHalfY, skirtBotZ - 0.2 * millimeter),
            "corner2" : vector(inHalfX, inHalfY, seamZ + 0.4 * millimeter)
        });
        opFillet(context, id + "skirtInFillet", {
            "entities" : qEdgeTopologyFilter(qParallelEdges(qOwnedByBody(qCreatedBy(id + "skInBox", EntityType.BODY), EntityType.EDGE), Z_DIRECTION), EdgeTopology.TWO_SIDED),
            "radius" : inR
        });
        opBoolean(context, id + "subSkirtHole", {
            "tools" : qCreatedBy(id + "skInBox", EntityType.BODY),
            "targets" : skirtBody,
            "operationType" : BooleanOperationType.SUBTRACTION
        });

        // Trim skirt ONLY at USB1 inner opening (Y = 8.61..18.41) and H1 opening (East)
        // Keeping West skirt at Y = 7.1..8.61 & 18.41..19.9 fills the inner USB cheeks up to seamZ!
        fCuboid(context, id + "trimUsbWest", {
            "corner1" : vector(-outHalfX - 1 * millimeter, py(8.61), skirtBotZ - 0.5 * millimeter),
            "corner2" : vector(px(1.5), py(18.41), seamZ + 0.5 * millimeter)
        });
        fCuboid(context, id + "trimH1East", {
            "corner1" : vector(px(45.5), py(11.0), skirtBotZ - 0.5 * millimeter),
            "corner2" : vector(outHalfX + 1 * millimeter, outHalfY + 1 * millimeter, seamZ + 0.5 * millimeter)
        });
        opBoolean(context, id + "subSkirtTrim", {
            "tools" : qUnion([
                qCreatedBy(id + "trimUsbWest", EntityType.BODY),
                qCreatedBy(id + "trimH1East", EntityType.BODY)
            ]),
            "targets" : skirtBody,
            "operationType" : BooleanOperationType.SUBTRACTION
        });

        // Add 4x 45-deg Snap-Fit Beads on Skirt outer faces
        var beadTools = [topBody, skirtBody];
        for (var i = 0; i < size(snapSpans); i += 1)
        {
            const sp = snapSpans[i];
            const skB = newSketchOnPlane(context, id + ("skB" ~ i), {
                "sketchPlane" : plane(vector(sp.x1 + 0.3 * millimeter, 0 * millimeter, 0 * millimeter), X_DIRECTION, Y_DIRECTION)
            });
            const yBase = sp.y - sp.sign * (definition.snapClearance + 0.05 * millimeter);
            const yTip  = sp.y + sp.sign * (0.24 * millimeter - definition.snapClearance);
            skPolyline(skB, "b", {
                "points" : [
                    vector(yBase, grooveZ - 0.42 * millimeter),
                    vector(yTip,  grooveZ),
                    vector(yBase, grooveZ + 0.42 * millimeter),
                    vector(yBase, grooveZ - 0.42 * millimeter)
                ]
            });
            skSolve(skB);
            opExtrude(context, id + ("extB" ~ i), {
                "entities" : qSketchRegion(id + ("skB" ~ i)),
                "direction" : X_DIRECTION,
                "endBound" : BoundingType.BLIND,
                "endDepth" : (sp.x2 - sp.x1) - 0.6 * millimeter
            });
            opDeleteBodies(context, id + ("delSkB" ~ i), { "entities" : qCreatedBy(id + ("skB" ~ i), EntityType.BODY) });
            beadTools = append(beadTools, qCreatedBy(id + ("extB" ~ i), EntityType.BODY));
        }

        // Add Top Lid Hold-Down Alignment Sockets engaging TL & BR M2 alignment pins (2.45+ mm engagement)
        for (var i = 0; i < size(standoffs); i += 1)
        {
            const s = standoffs[i];
            const skH = newSketchOnPlane(context, id + ("skHD" ~ i), {
                "sketchPlane" : plane(vector(0 * millimeter, 0 * millimeter, 0.05 * millimeter), Z_DIRECTION, X_DIRECTION)
            });
            skCircle(skH, "out", { "center" : vector(s.x, s.y), "radius" : 2.00 * millimeter });
            skCircle(skH, "in",  { "center" : vector(s.x, s.y), "radius" : 1.07 * millimeter });
            skSolve(skH);
            opExtrude(context, id + ("extHD" ~ i), {
                "entities" : qSketchRegion(id + ("skHD" ~ i), true),
                "direction" : Z_DIRECTION,
                "endBound" : BoundingType.BLIND,
                "endDepth" : seamZ + 0.2 * millimeter
            });
            opDeleteBodies(context, id + ("delSkHD" ~ i), { "entities" : qCreatedBy(id + ("skHD" ~ i), EntityType.BODY) });
            beadTools = append(beadTools, qCreatedBy(id + ("extHD" ~ i), EntityType.BODY));
        }

        opBoolean(context, id + "unionTop", {
            "tools" : qUnion(beadTools),
            "operationType" : BooleanOperationType.UNION
        });
        topBody = qCreatedBy(id + "topPlate", EntityType.BODY);

        // 2b. Cut Top Lid Openings: H1 1x5P Target Header (X=43.13..46.53, Y=11.55..24.91) + LED1 & LED2 2.2 mm holes
        //     NOTE: H2 self-prog header is intentionally kept closed under the lid!
        fCuboid(context, id + "cutH1", {
            "corner1" : vector(px(43.13), py(11.55), seamZ - 0.2 * millimeter),
            "corner2" : vector(px(46.53), py(24.91), topExtZ + 0.5 * millimeter)
        });
        opFillet(context, id + "h1Fillet", {
            "entities" : qEdgeTopologyFilter(qParallelEdges(qOwnedByBody(qCreatedBy(id + "cutH1", EntityType.BODY), EntityType.EDGE), Z_DIRECTION), EdgeTopology.TWO_SIDED),
            "radius" : 0.45 * millimeter
        });

        const ledR = definition.ledHoleDia / 2;
        fCylinder(context, id + "cutLed1", {
            "bottomCenter" : vector(px(13.08), py(24.13), seamZ - 0.2 * millimeter),
            "topCenter" : vector(px(13.08), py(24.13), topExtZ + 0.5 * millimeter),
            "radius" : ledR
        });
        fCylinder(context, id + "cutLed2", {
            "bottomCenter" : vector(px(44.32), py(9.78), seamZ - 0.2 * millimeter),
            "topCenter" : vector(px(44.32), py(9.78), topExtZ + 0.5 * millimeter),
            "radius" : ledR
        });
        opBoolean(context, id + "subTopCuts", {
            "tools" : qUnion([
                qCreatedBy(id + "cutH1", EntityType.BODY),
                qCreatedBy(id + "cutLed1", EntityType.BODY),
                qCreatedBy(id + "cutLed2", EntityType.BODY)
            ]),
            "targets" : topBody,
            "operationType" : BooleanOperationType.SUBTRACTION
        });

        // 2c. Debossed Top Labels (0.40 mm deep from topExtZ, zero-support when printed face-down)
        if (definition.addLabels)
        {
            const labelDepth = 0.40 * millimeter;
            const skTxt = newSketchOnPlane(context, id + "skTxt", {
                "sketchPlane" : plane(vector(0 * millimeter, 0 * millimeter, topExtZ), Z_DIRECTION, X_DIRECTION)
            });

            // H1 Pinout Labels (aligned to pads at Y = 23.24, 20.70, 18.16, 15.62, 13.08)
            const h1Labels = [
                { "text" : "GND", "y" : 23.24 },
                { "text" : "PWR", "y" : 20.70 },
                { "text" : "3V3", "y" : 18.16 },
                { "text" : "SWM", "y" : 15.62 },
                { "text" : "RST", "y" : 13.08 }
            ];
            for (var i = 0; i < size(h1Labels); i += 1)
            {
                const lb = h1Labels[i];
                skText(skTxt, "h1_" ~ i, {
                    "text" : lb.text,
                    "fontName" : "OpenSans-Bold.ttf",
                    "firstCorner" : vector(px(36.8), py(lb.y - 0.85)),
                    "secondCorner" : vector(px(42.4), py(lb.y + 0.85))
                });
            }

            // LED1 (5V) and LED2 (PWR) labels
            skText(skTxt, "led1Lbl", {
                "text" : "5V",
                "fontName" : "OpenSans-Bold.ttf",
                "firstCorner" : vector(px(11.3), py(20.6)),
                "secondCorner" : vector(px(14.9), py(22.2))
            });
            skText(skTxt, "led2Lbl", {
                "text" : "PWR",
                "fontName" : "OpenSans-Bold.ttf",
                "firstCorner" : vector(px(36.8), py(8.9)),
                "secondCorner" : vector(px(42.4), py(10.6))
            });

            // Board Title on clear center-west roof area
            skText(skTxt, "title1", {
                "text" : "TLSR",
                "fontName" : "OpenSans-Bold.ttf",
                "firstCorner" : vector(px(12.0), py(14.2)),
                "secondCorner" : vector(px(26.0), py(17.5))
            });
            skText(skTxt, "title2", {
                "text" : "FLASHER",
                "fontName" : "OpenSans-Bold.ttf",
                "firstCorner" : vector(px(12.0), py(10.0)),
                "secondCorner" : vector(px(31.5), py(13.0))
            });

            skSolve(skTxt);
            opExtrude(context, id + "extTxt", {
                "entities" : qSketchRegion(id + "skTxt", true),
                "direction" : -Z_DIRECTION,
                "endBound" : BoundingType.BLIND,
                "endDepth" : labelDepth
            });
            opDeleteBodies(context, id + "delSkTxt", { "entities" : qCreatedBy(id + "skTxt", EntityType.BODY) });
            opBoolean(context, id + "subLabels", {
                "tools" : qCreatedBy(id + "extTxt", EntityType.BODY),
                "targets" : topBody,
                "operationType" : BooleanOperationType.SUBTRACTION
            });
        }

        // =========================================================================
        // 3. POSITIONING: Seat Bottom Shell on Z=0 (or Print Layout Side-by-Side)
        // =========================================================================
        opTransform(context, id + "seatBot", {
            "bodies" : botBody,
            "transform" : transform(vector(0 * millimeter, 0 * millimeter, -botExtZ))
        });

        if (definition.printLayout)
        {
            // Flip Top Lid 180 deg around X (roof flat on Z=0) and place +Y beside Bottom Shell
            const rotFlip = rotationMatrix3d(X_DIRECTION, 180 * degree);
            const flipT   = transform(rotFlip, vector(0 * millimeter, 2 * outHalfY + 8 * millimeter, topExtZ));
            opTransform(context, id + "flipTop", {
                "bodies" : topBody,
                "transform" : flipT
            });
        }
        else
        {
            // Assembled position seated cleanly on Z=0
            opTransform(context, id + "seatTop", {
                "bodies" : topBody,
                "transform" : transform(vector(0 * millimeter, 0 * millimeter, -botExtZ))
            });
        }
    });
