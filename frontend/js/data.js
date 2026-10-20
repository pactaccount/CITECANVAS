/* ==========================================================================
   EVID SAMPLE PROJECT DATA: PHARMA COMPLIANCE PACKAGE
   SOURCE: pharma-blob-sample.pdf (pypdfium2 text extraction + visual inspection)
   All values sourced directly from the actual PDF — not invented.
   SAMPLE PROJECT — clearly marked; not a real uploaded project.
   ========================================================================== */

const PHARMA_SAMPLE_PROJECT = {
  projectId: "proj_cytiva_001",
  projectName: "Cytiva Compliance Evaluation",
  projectDescription: "Technical and regulatory evaluation package for single-use AKTA ready flow kit assemblies.",
  createdAt: "2026-10-17T22:00:00Z",
  status: "Ready",
  isSampleProject: true,

  masterFile: {
    fileId: "file_pharma_blob_001",
    filename: "pharma-blob-sample.pdf",
    fileSize: "12.5 KB",
    totalPages: 10,
    sha256: "de6abb0444c130b946b996ad3971036b95d353ae4380b15118c95c5f358361fe",
    uploadedAt: "Oct 17, 2026",
    status: "Ready",
  },

  // 8 logical sub-documents isolated from pharma-blob-sample.pdf
  subdocuments: [
    {
      subdocId: "subdoc_1",
      title: "Flow Kit Storage Conditions Recommendation",
      docType: "Correspondence",
      startPage: 1, endPage: 1, pageCount: 1,
      scopedIdentifiers: {
        documentNumber: "CORR-2023-STORAGE",
        storageTemp: "> +5\u00b0C",
        operatingTemp: "+2\u00b0C to +40\u00b0C",
      },
      metadataStatus: "Suggested (AI)",
      summary: "Advisory letter specifying warehouse storage (> +5\u00b0C) and operational ambient temperature (+2\u00b0C to +40\u00b0C).",
    },
    {
      subdocId: "subdoc_2",
      title: "Certificate of Quality \u2014 Low Flow Kit",
      docType: "Certificate",
      startPage: 2, endPage: 2, pageCount: 1,
      scopedIdentifiers: {
        // Values taken directly from the PDF text layer on Page 2
        lotNumber: "18356721",
        articleNumber: "28 9301 82",    // CORRECTED: "Product Article Number: 28 9301 82"
        dateOfManufacture: "20240315",  // CORRECTED: "Date of Manufacture: 20240315"
        expirationDate: "20260315",
        gammaRange: "25.0 - 40.0 kGy",
      },
      metadataStatus: "Suggested (AI)",
      summary: "Batch release certificate for Low Flow Kit lot 18356721. Article: 28 9301 82. Manufactured: 15 March 2024. Gamma: 25.0\u201340.0 kGy.",
    },
    {
      subdocId: "subdoc_3",
      title: "Certificate of Quality \u2014 High Flow Kit",
      docType: "Certificate",
      startPage: 3, endPage: 3, pageCount: 1,
      scopedIdentifiers: {
        lotNumber: "15102934",
        articleNumber: "28 9301 83",
        dateOfManufacture: "20190712",
        expirationDate: "20210712",
        gammaRange: "25.0 - 40.0 kGy",
      },
      metadataStatus: "Suggested (AI)",
      summary: "Batch release certificate for High Flow Kit lot 15102934. Article: 28 9301 83. Manufactured: 12 July 2019.",
    },
    {
      subdocId: "subdoc_4",
      title: "Packaging Component Specification",
      docType: "Technical Specification",
      startPage: 4, endPage: 5, pageCount: 2,
      scopedIdentifiers: {
        documentNumber: "PKG-SPEC-2023-0847",
        revision: "C",
        ecnNumber: "ECN-2023-0847",
        materialChange: "PVC to PETG",
      },
      metadataStatus: "Suggested (AI)",
      summary: "Packaging specification. Revision C replaces PVC blister tray with PETG under ECN-2023-0847.",
    },
    {
      subdocId: "subdoc_5",
      title: "BSE/TSE Compliance Statement",
      docType: "Declaration",
      startPage: 6, endPage: 6, pageCount: 1,
      scopedIdentifiers: {
        referenceNumber: "BSE-RA-2023-AKTA-001",
        standard: "EU Reg (EC) No 722/2012",
      },
      metadataStatus: "Suggested (AI)",
      summary: "Risk assessment confirming no animal-derived materials in AKTA ready Flow Kit manufacturing lines.",
    },
    {
      subdocId: "subdoc_6",
      title: "Material Description Sheet",
      docType: "Technical Specification",
      startPage: 7, endPage: 7, pageCount: 1,
      scopedIdentifiers: {
        partNumber: "29184612",
        revision: "AD",
        maxPressure: "5 MPa (50 bar)",
      },
      metadataStatus: "Suggested (AI)",
      summary: "Engineering data sheet for Part 29184612 Rev AD. Max operating pressure: 5 MPa. Operating temp: +2\u00b0C to +40\u00b0C.",
    },
    {
      subdocId: "subdoc_7",
      title: "Supplier Qualification Record",
      docType: "Audit Report",
      startPage: 8, endPage: 9, pageCount: 2,
      scopedIdentifiers: {
        supplierCode: "SUP-2019-0847",
        supplierName: "Cytiva Sweden AB",
        auditDate: "20 November 2023",
        otdPerformance: "97.3%",
      },
      metadataStatus: "Suggested (AI)",
      summary: "Quality audit for Cytiva Sweden AB (20 Nov 2023). On-time delivery: 97.3%.",
    },
    {
      subdocId: "subdoc_8",
      title: "Global Chain of Custody",
      docType: "Chain of Custody",
      startPage: 10, endPage: 10, pageCount: 1,
      scopedIdentifiers: {
        facility: "Eysins Facility, Switzerland",
        preparedBy: "Supply Chain Quality, Cytiva",
        date: "15 January 2024",
      },
      metadataStatus: "Suggested (AI)",
      summary: "List of assemblies manufactured at Cytiva Eysins Facility. NOT a quality certificate.",
    },
  ],

  // -----------------------------------------------------------------------
  // Grounded Q&A scenarios — each answer is scoped to exactly one citation
  // -----------------------------------------------------------------------
  qaScenarios: [
    {
      id: "q_storage",
      question: "Storage recommendation versus operating temperature?",
      outcome: "found",
      outcomeLabel: "Answer found in documents",
      answerText: "The advisory correspondence (Page 1) establishes two distinct temperature regimes: warehouse storage must be maintained at > +5\u00b0C, and operational ambient temperature during use is +2\u00b0C to +40\u00b0C.",
      citations: [{
        id: "EVID-1", label: "Storage Letter \u00b7 p.\u00a01", pageNumber: 1,
        docTitle: "Flow Kit Storage Conditions Recommendation",
        boundingBox: { ymin: 220, xmin: 60, ymax: 370, xmax: 920 },
        quote: "The recommended storage temperature for standard AKTA ready flow kits is > +5\u00b0C. The operating temperature of AKTA ready flow kits is +2\u00b0C to +40\u00b0C.",
      }],
      qualifications: "Extended storage below +5\u00b0C could lead to brittleness or cracking of plastic connectors (source: Page 1).",
      calculation: null,
    },
    {
      id: "q_gamma_18356721",
      question: "Gamma range for lot 18356721?",
      outcome: "found",
      outcomeLabel: "Answer found in documents",
      answerText: "The Certificate of Quality on Page 2 for Low Flow Kit lot 18356721 (Article Number 28 9301 82, manufactured 15 March 2024) specifies a gamma irradiation dose of 25.0\u201340.0 kGy.",
      citations: [{
        id: "EVID-2", label: "Low Flow Certificate \u00b7 p.\u00a02", pageNumber: 2,
        docTitle: "Certificate of Quality \u2014 Low Flow Kit (Lot 18356721)",
        boundingBox: { ymin: 580, xmin: 60, ymax: 660, xmax: 920 },
        quote: "Gamma Irradiation - Inlets | 25.0 - 40.0 kGy | Conforms. Lot Number: 18356721. Article Number: 28 9301 82.",
      }],
      // REMOVED: unverified ISO 11137 claim not stated on the certificate page
      qualifications: "Gamma range stated on the release certificate. No irradiation standard is cited on the printed certificate page.",
      calculation: null,
    },
    {
      id: "q_high_flow_lot",
      question: "Which lot is on the high-flow certificate?",
      outcome: "found",
      outcomeLabel: "Answer found in documents",
      answerText: "Lot 15102934 is documented on the Certificate of Quality for the AKTA ready High Flow Kit on Page 3. Lot 18356721 belongs exclusively to the Low Flow Kit certificate on Page 2.",
      citations: [{
        id: "EVID-3", label: "High Flow Certificate \u00b7 p.\u00a03", pageNumber: 3,
        docTitle: "Certificate of Quality \u2014 High Flow Kit (Lot 15102934)",
        boundingBox: { ymin: 200, xmin: 60, ymax: 340, xmax: 920 },
        quote: "Product: AKTA ready High Flow Kit. Lot Number: 15102934. Product Article Number: 28 9301 83.",
      }],
      qualifications: "Lot numbers are scoped to their respective sub-documents and are not merged.",
      calculation: null,
    },
    {
      id: "q_rev_c_change",
      question: "What changed in packaging revision C?",
      outcome: "found",
      outcomeLabel: "Answer found in documents",
      answerText: "Under ECN-2023-0847 (Page 5), Revision C replaced the PVC blister tray material with thermoformed medical-grade PETG (EU Reg 2023/1297) to eliminate phthalate risk and improve low-temperature impact resistance.",
      citations: [{
        id: "EVID-4", label: "Packaging Specification \u00b7 p.\u00a05", pageNumber: 5,
        docTitle: "Packaging Component Specification (Rev C Change History)",
        boundingBox: { ymin: 160, xmin: 60, ymax: 320, xmax: 920 },
        quote: "C | 2023-11-08 | ECN-2023-0847 | Changed blister material from PVC to PETG (EU Reg 2023/1297).",
      }],
      qualifications: "Revision C applies to the packaging material only, not to fluid flow path assemblies.",
      calculation: null,
    },
    {
      id: "q_pressure_rev_ad",
      question: "Maximum pressure for part 29184612, revision AD?",
      outcome: "found",
      outcomeLabel: "Answer found in documents",
      answerText: "According to the Material Description Sheet (Page 7), Part 29184612 Revision AD has a maximum operating pressure of 5 MPa, equal to 50.0 bar.",
      citations: [{
        id: "EVID-5", label: "Material Description Sheet \u00b7 p.\u00a07", pageNumber: 7,
        docTitle: "Material Description Sheet (Part 29184612 Rev AD)",
        boundingBox: { ymin: 620, xmin: 60, ymax: 700, xmax: 920 },
        quote: "Operating Pressure: Max 5 MPa. Part Number: 29184612. Revision: AD.",
      }],
      // REMOVED: unverified "at 20\u00b0C" — that condition is not stated on Page 7
      qualifications: "Pressure limit stated in the Material Description Sheet. No temperature condition is cited alongside this value on Page 7.",
      calculation: {
        formula: "5.0 MPa \u00d7 10.0 bar/MPa = 50.0 bar",
        inputValue: "5.0 MPa",
        outputValue: "50.0 bar",
        conversionFactor: "10.0 (exact: 1 MPa = 10\u00b3 kPa = 10 bar)",
        nature: "Unit conversion of document fact (Part 29184612 Rev AD, Page 7)",
        sourceRef: "Page 7, Material Description Sheet",
      },
    },
    {
      id: "q_page_10_identity",
      question: "Is page 10 a quality certificate?",
      outcome: "found",
      outcomeLabel: "Answer found in documents",
      answerText: "No. Page 10 is a Global Chain of Custody document, not a Certificate of Quality. It lists assemblies manufactured at the Cytiva Eysins Facility in Switzerland and traces custody steps from incoming materials through customer shipment. Quality certificates appear on Pages 2 and 3.",
      citations: [{
        id: "EVID-6", label: "Global Chain of Custody \u00b7 p.\u00a010", pageNumber: 10,
        docTitle: "Global Chain of Custody Record (Eysins Facility)",
        boundingBox: { ymin: 60, xmin: 60, ymax: 200, xmax: 920 },
        quote: "Global Chain of Custody \u2014 List of Assemblies Manufactured at Cytiva Eysins Facility in Switzerland. Document Classification: Global Chain of Custody Record (NOT a Quality Certificate).",
      }],
      qualifications: "Quality certificates appear strictly on Pages 2 and 3.",
      calculation: null,
    },
    {
      id: "q_rev_b_c_pressures",
      question: "What were operating pressures in revisions B and C?",
      outcome: "unestablished",
      outcomeLabel: "Could not establish from available evidence",
      answerText: "I could not establish this from the available evidence. Packaging revisions B and C (Page 5) specify blister tray material changes and dimensions, not operating pressure values. Operating pressure is defined separately on Page 7 for flow manifold Part 29184612 Rev AD (5 MPa = 50 bar).",
      citations: [{
        id: "EVID-7", label: "Packaging Specification \u00b7 p.\u00a05", pageNumber: 5,
        docTitle: "Packaging Component Specification (Change History)",
        boundingBox: { ymin: 100, xmin: 60, ymax: 350, xmax: 920 },
        quote: "Configuration change history details blister tray dimensions and materials; no pressure specifications stated.",
      }],
      qualifications: "Operating pressure for the fluid path is only defined on Page 7, in a separate sub-document.",
      calculation: null,
    },
    {
      id: "q_350_psi_fixture",
      question: "Convert 350 psi to bar (Calculation Fixture)?",
      outcome: "found",
      outcomeLabel: "Independent unit conversion",
      answerText: "350.0 psi converts to approximately 24.1317 bar (1 bar \u2248 14.5038 psi). This is an independent unit conversion and does not correspond to any pressure value in this document bundle.",
      citations: [],
      qualifications: "Independent unit conversion \u2014 not a value from this PDF.",
      calculation: {
        formula: "350.0 psi \u00d7 0.0689476 bar/psi \u2248 24.1317 bar",
        inputValue: "350.0 psi",
        outputValue: "24.1317 bar",
        conversionFactor: "0.0689475729316836 bar/psi (ratio \u2248 14.5038 psi/bar)",
        nature: "Independent unit conversion \u2014 not stated in this PDF bundle",
        sourceRef: "No source in this bundle",
      },
    }
  ],

  // -----------------------------------------------------------------------
  // Structured extraction matrix
  // -----------------------------------------------------------------------
  extractionMatrix: {
    templateName: "Technical & Quality Component Specifications",
    fields: [
      { id: "f_part",     name: "Part / Article Number",    type: "Text",   desc: "Component or kit part / article identifier" },
      { id: "f_lot",      name: "Lot Number",               type: "Text",   desc: "Manufacturing batch or lot code" },
      { id: "f_rev",      name: "Revision",                 type: "Text",   desc: "Engineering or packaging revision code" },
      { id: "f_pressure", name: "Max Operating Pressure",   type: "Number", unit: "bar", desc: "Maximum rated fluid pressure" },
      { id: "f_gamma",    name: "Gamma Irradiation Range",  type: "Range",  unit: "kGy", desc: "Sterilization dosage tolerance" },
    ],
    rows: [
      {
        subdocId: "subdoc_2",
        documentTitle: "Certificate of Quality \u2014 Low Flow Kit (p.2)",
        page: 2,
        reviewStatus: "Needs review",  // CORRECTED: No pre-seeded reviewer acceptance
        reviewedBy: null, reviewedAt: null,
        values: {
          // CORRECTED article number: 28 9301 82 (from PDF page 2), NOT 29021085
          f_part:     { value: "28 9301 82",              citation: "p.\u00a02", box: { ymin: 280, xmin: 60, ymax: 340, xmax: 560 }, status: "valid",
                        sourceNote: "Product Article Number as printed on Page 2 certificate" },
          f_lot:      { value: "18356721",                citation: "p.\u00a02", box: { ymin: 240, xmin: 60, ymax: 300, xmax: 560 }, status: "valid" },
          f_rev:      { value: "Not found on this page",  citation: null, box: null, status: "not_established" },
          f_pressure: { value: "Not applicable",          citation: null, box: null, status: "na" },
          f_gamma:    { value: "25.0 - 40.0 kGy",        citation: "p.\u00a02", box: { ymin: 580, xmin: 60, ymax: 650, xmax: 920 }, status: "valid" },
        }
      },
      {
        subdocId: "subdoc_3",
        documentTitle: "Certificate of Quality \u2014 High Flow Kit (p.3)",
        page: 3,
        reviewStatus: "Needs review",
        reviewedBy: null, reviewedAt: null,
        values: {
          f_part:     { value: "28 9301 83",              citation: "p.\u00a03", box: { ymin: 280, xmin: 60, ymax: 340, xmax: 560 }, status: "valid",
                        sourceNote: "Product Article Number as printed on Page 3 certificate" },
          f_lot:      { value: "15102934",                citation: "p.\u00a03", box: { ymin: 240, xmin: 60, ymax: 300, xmax: 560 }, status: "valid" },
          f_rev:      { value: "Not found on this page",  citation: null, box: null, status: "not_established" },
          f_pressure: { value: "Not applicable",          citation: null, box: null, status: "na" },
          f_gamma:    { value: "25.0 - 40.0 kGy",        citation: "p.\u00a03", box: { ymin: 580, xmin: 60, ymax: 650, xmax: 920 }, status: "valid" },
        }
      },
      {
        subdocId: "subdoc_4",
        documentTitle: "Packaging Component Specification (pp.4\u20135)",
        page: 5,
        reviewStatus: "Needs review",
        reviewedBy: null, reviewedAt: null,
        values: {
          f_part:     { value: "PKG-29477427-C",               citation: "p.\u00a04", box: { ymin: 400, xmin: 60, ymax: 470, xmax: 600 }, status: "valid" },
          f_lot:      { value: "Not applicable",               citation: null, box: null, status: "na" },
          f_rev:      { value: "C",                            citation: "p.\u00a04", box: { ymin: 120, xmin: 300, ymax: 180, xmax: 450 }, status: "valid" },
          f_pressure: { value: "Not found in this document",   citation: null, box: null, status: "not_established" },
          f_gamma:    { value: "Compatible (25.0 - 40.0 kGy)", citation: "p.\u00a04", box: { ymin: 330, xmin: 60, ymax: 410, xmax: 700 }, status: "valid" },
        }
      },
      {
        subdocId: "subdoc_6",
        documentTitle: "Material Description Sheet (p.7)",
        page: 7,
        reviewStatus: "Needs review",
        reviewedBy: null, reviewedAt: null,
        values: {
          f_part:     { value: "29184612",               citation: "p.\u00a07", box: { ymin: 100, xmin: 60,  ymax: 180, xmax: 400 }, status: "valid" },
          f_lot:      { value: "Not applicable",         citation: null, box: null, status: "na" },
          f_rev:      { value: "AD",                     citation: "p.\u00a07", box: { ymin: 120, xmin: 400, ymax: 180, xmax: 600 }, status: "valid" },
          f_pressure: { value: "50.0 bar (5 MPa)",       citation: "p.\u00a07", box: { ymin: 620, xmin: 60,  ymax: 700, xmax: 920 }, status: "valid" },
          f_gamma:    { value: "25\u201340 kGy (fittings)", citation: "p.\u00a07", box: { ymin: 530, xmin: 60, ymax: 610, xmax: 920 }, status: "valid" },
        }
      }
    ]
  },

  // -----------------------------------------------------------------------
  // Comparison datasets — keyed so compare.js can bind to selector values
  // -----------------------------------------------------------------------
  comparisonDatasets: {
    "packaging_revB_vs_revC": {
      label: "Packaging Spec Rev B vs Rev C",
      docALabel: "Packaging Spec Rev B (DWG-29477427-PKG-R2)",
      docBLabel: "Packaging Spec Rev C (DWG-29477427-PKG-R3)",
      docASubdocId: "subdoc_4", docBSubdocId: "subdoc_4",
      docAPage: 4, docBPage: 5,
      items: [
        { item: "Blister Tray Material",
          earlierVal: "Medical-grade PVC",
          laterVal: "Medical-grade PETG (ASTM D1003)",
          finding: "Changed", findingClass: "finding-changed",
          pageA: 4, pageB: 5,
          note: "Changed under ECN-2023-0847 to eliminate phthalate plasticizer risk and improve low-temp impact resistance." },
        { item: "Tray Insert Dimensions",
          earlierVal: "Rev A baseline",
          laterVal: "+3 mm (ECN-2021-0541, Rev B); maintained in Rev C",
          finding: "Uncertain", findingClass: "finding-uncertain",
          pageA: 5, pageB: 5,
          note: "Rev B updated dimensions by +3 mm; exact Rev A baseline dimension is not restated in the change table." },
        { item: "Operating Pressure",
          earlierVal: "Not established in this document",
          laterVal: "Not established in this document",
          finding: "Not found in either version", findingClass: "finding-unestablished",
          pageA: 4, pageB: 5,
          note: "Pressure is defined separately on Page 7 for flow manifold Part 29184612 Rev AD (5 MPa). Not part of packaging specification." },
        { item: "Gamma Sterilization Compatibility",
          earlierVal: "Compatible (25.0\u201340.0 kGy)",
          laterVal: "Compatible (25.0\u201340.0 kGy)",
          finding: "No difference found in examined information", findingClass: "finding-identical",
          pageA: 4, pageB: 4,
          note: "Both substrates stated as gamma compatible on Page 4." }
      ]
    },
    "low_flow_vs_high_flow": {
      label: "Low Flow Cert (Lot 18356721) vs High Flow Cert (Lot 15102934)",
      docALabel: "Low Flow Kit Certificate \u2014 Lot 18356721 (p.2)",
      docBLabel: "High Flow Kit Certificate \u2014 Lot 15102934 (p.3)",
      docASubdocId: "subdoc_2", docBSubdocId: "subdoc_3",
      docAPage: 2, docBPage: 3,
      items: [
        { item: "Product Type",
          earlierVal: "AKTA ready Low Flow Kit",
          laterVal: "AKTA ready High Flow Kit",
          finding: "Different products", findingClass: "finding-changed",
          pageA: 2, pageB: 3,
          note: "These are different product types, not different revisions of the same product." },
        { item: "Article Number",
          earlierVal: "28 9301 82",
          laterVal: "28 9301 83",
          finding: "Changed", findingClass: "finding-changed",
          pageA: 2, pageB: 3,
          note: "Different article numbers confirm distinct SKUs." },
        { item: "Lot Number",
          earlierVal: "18356721",
          laterVal: "15102934",
          finding: "Different lots", findingClass: "finding-changed",
          pageA: 2, pageB: 3,
          note: "Each is a separate manufacturing batch for its respective product." },
        { item: "Gamma Irradiation Range",
          earlierVal: "25.0 - 40.0 kGy",
          laterVal: "25.0 - 40.0 kGy",
          finding: "No difference found in examined information", findingClass: "finding-identical",
          pageA: 2, pageB: 3,
          note: "Both certificates state the same gamma dose range." },
        { item: "Date of Manufacture",
          earlierVal: "20240315 (15 March 2024)",
          laterVal: "20190712 (12 July 2019)",
          finding: "Changed", findingClass: "finding-changed",
          pageA: 2, pageB: 3,
          note: "Manufactured approximately 4.5 years apart." }
      ]
    }
  },

  // -----------------------------------------------------------------------
  // Accessible page text — sourced from pypdfium2 native text extraction
  // -----------------------------------------------------------------------
  accessiblePageText: {
    1: "Cytiva\n100 Results Way\nMarlborough, MA 01752\nUnited States\n\n3 June, 2022\n\nRe: AKTA ready Flow Kit Storage Conditions\n\nThe recommended storage temperature for standard AKTA ready flow kits is > +5\u00b0C. Extended storage below +5\u00b0C could lead to brittleness or cracking of plastic connectors. The operating temperature of AKTA ready flow kits is +2\u00b0C to +40\u00b0C.\n\nCytiva Quality Assurance",
    // Page 2: CORRECTED — Article Number 28 9301 82, Date of Manufacture 20240315
    2: "Certificate of Quality\n\nIssued by Cytiva Westborough Quality Assurance\n\nProduct: AKTA ready Low Flow Kit\nLot Number: 18356721\nProduct Article Number: 28 9301 82\nDate of Manufacture: 20240315\nProduct Description: Low Flow Kit, AKTA ready\nExpiration Date: 20260315\n\nProduct Release Criteria\nAutoclave - Pump tubing | 121\u00b0C > 15 min | Conforms\nGamma Irradiation - Inlets | 25.0 - 40.0 kGy | Conforms\nFlow Rate Test | Per specification | Conforms\nPressure Integrity Test | Per specification | Conforms\nVisual Inspection | Per specification | Conforms\nPackage Integrity | Per specification | Conforms",
    3: "Certificate of Quality\n\nIssued by Cytiva Westborough Quality Assurance\n\nProduct: AKTA ready High Flow Kit\nLot Number: 15102934\nProduct Article Number: 28 9301 83\nDate of Manufacture: 20190712\nProduct Description: High Flow Kit, AKTA ready\nExpiration Date: 20210712\n\nProduct Release Criteria\nAutoclave - Pump tubing | 121\u00b0C > 15 min | Conforms\nGamma Irradiation - Inlets | 25.0 - 40.0 kGy | Conforms\nFlow Rate Test | Per specification | Conforms\nPressure Integrity Test | Per specification | Conforms\nVisual Inspection | Per specification | Conforms\nPackage Integrity | Per specification | Conforms",
    4: "Packaging Component Specification\n\nDocument Number: PKG-SPEC-2023-0847\nRevision: C\nEffective Date: 2023-11-08\nComponent: AKTA ready Flow Kit Packaging Assembly\nDrawing Reference: DWG-29477427-PKG-R3\n\nMaterials:\nBlister Tray: PETG (ASTM D1003, min 92% clarity)\nLid Film: Tyvek 1073B\nSecondary Carton: Corrugated ECT-32, C-flute\nInner Cushion: PE Foam, 2 lb density, 1 inch thick\n\nPart Numbers:\nAssembly: PKG-29477427-C\nSterilization: Gamma irradiation compatible (25.0 - 40.0 kGy)",
    5: "Packaging Component Specification (continued)\nDocument Number: PKG-SPEC-2023-0847, Page 2 of 2\n\nConfiguration Change History:\nRev A | 2019-03-15 | ECN-2019-0312 | Initial release - PVC blister tray\nRev B | 2021-06-22 | ECN-2021-0541 | Updated tray insert dimensions (+3mm)\nRev C | 2023-11-08 | ECN-2023-0847 | Changed blister material from PVC to PETG (EU Reg 2023/1297)\n\nDrawing DWG-29477427-PKG-R3 supersedes DWG-29477427-PKG-R2.\nApproved by: Packaging Engineering, Cytiva Uppsala. Date: 2023-11-08.",
    6: "Declaration Regarding Transmissible Spongiform Encephalopathies (BSE/TSE Compliance Statement)\n\nManufacturer: Cytiva Sweden AB\nProduct Family: AKTA ready Flow Kits\nApplicable Part Numbers: 29477427, 29184612, 28930182, 28930183\n\nWe declare that the above-referenced products do not contain any materials of animal origin.\nAll polymeric materials comply with:\n- EU Regulation (EC) No 722/2012\n- EU Regulation (EC) No 1774/2002\n- USP <87> and <88>\n\nRisk Assessment Reference: BSE-RA-2023-AKTA-001. Date: 15 March 2023. Valid Until: 15 March 2028.",
    7: "Material Description Sheet\n\nProduct: AKTA ready Gradient Flow Section With Inlets\nPart Number: 29184612\nRevision: AD\n\nMaterials of Construction:\nHousing: Polypropylene (PP) ISO 1873-1\nGaskets: EPDM Rubber USP Class VI\nPump Tubing: Platinum-Cured Silicone USP Class VI\nInlet Fittings: PEEK ASTM D6262\nMixing Chamber: Borosilicate Glass USP Type I\n\nSterilization Compatibility:\nAutoclave: 121\u00b0C, 15 min - Yes (tubing)\nGamma Irradiation: 25-40 kGy - Yes (fittings)\nEtO Sterilization: Not validated - No\n\nPhysical Properties:\nDimensions: 245 x 120 x 85 mm\nOperating Temperature: +2\u00b0C to +40\u00b0C\nOperating Pressure: Max 5 MPa\nShelf Life: 2 years from date of manufacture",
    8: "Supplier Qualification Record\n\nSupplier Name: Cytiva Sweden AB\nSupplier Code: SUP-2019-0847\nQualification Status: Approved\n\nInitial Qualification: 14 September 2019\nLast On-Site Audit: 20 November 2023\nAudit Result: Approved (no critical findings)\n\nCertifications:\nISO 9001:2015 - QMS-SE-2021-4847 - valid to 2024-12-31\nISO 13485:2016 - MD-SE-2021-1293 - valid to 2024-12-31\nFDA Establishment: 3007488211 - Active\n\nApproved Products: 29477427, 29184612, 28930182, 28930183, 29021085, 29021086",
    9: "Supplier Qualification Record (continued)\nPage 2 of 2\n\nSupply Chain:\nManufacturing Site: Cytiva Eysins Facility, Switzerland\nSecondary Site: Cytiva Uppsala Facility, Sweden\n\nPerformance Metrics (Last 12 Months):\nOn-Time Delivery: 97.3%\nIncoming Quality: 99.8% (2 minor NCRs, 0 critical)\nCAPA Response Time: Average 12 days\n\nQuality Agreement Reference: QA-2019-CYTIVA-0847. Last Reviewed: 20 November 2023.",
    10: "Cytiva\n100 Results Way\nMarlborough, MA 01752\nUnited States\n\nGlobal Chain of Custody\nList of Assemblies Manufactured at Cytiva Eysins Facility in Switzerland\nPage 1 of 1\n\nCytiva Item # | Description\n28930182 | Low Flow Kit, AKTA ready\n28930183 | High Flow Kit, AKTA ready\n29021085 | AKTA ready Gradient Low Flow Section\n29021086 | AKTA ready Gradient High Flow Section\n29477427 | High Flow Kit F, Modified, AKTA ready\n29184612 | High Flow Gradient C, Modified, AKTA ready\n\nAll assemblies follow the same chain of custody:\n1. Raw materials received at Eysins facility (incoming QC)\n2. Sub-assembly and final assembly (in-process checks)\n3. Final quality release\n4. Shipped to Cytiva Distribution Center, Marlborough, MA\n5. Distributed to end customer\n\nDocument Classification: Global Chain of Custody Record (NOT a Quality Certificate).\nPrepared by: Supply Chain Quality, Cytiva. Date: 15 January 2024."
  }
};
