import os
import json
import time
from lxml import etree
from tqdm import tqdm
from openai import OpenAI
import re
import xml.etree.ElementTree as ET

# ─────────────────────────────────────────────────────────────────────────────
#
CLIENT = OpenAI(
    api_key='api',
        organization='org',
        project='proj',
)
# ─────────────────────────────────────────────────────────────────────────────

# Define valid drugs if you wish to filter on specific IDs.
valid_drugs = {"DB13928"}  # e.g., valid_drugs = {"DB14596", "DB01323"}

# Optionally, list the fields you are interested in.
desired_fields = {
    # General Information
    "name", "description", "cas-number", "unii", "average-mass", "monoisotopic-mass", "state",
    # Pharmacological Information
    "indication", "pharmacodynamics", "mechanism-of-action", "toxicity", "metabolism", 
    "absorption", "half-life", "protein-binding", "route-of-elimination", 
    "volume-of-distribution", "clearance",
    # Chemical and Physical Properties
    "Molecular Formula", "SMILES", "logP", "Water Solubility", "Melting Point", "Molecular Weight",
    # Drug Classification and Categories
    "classification", "categories",
    # Regulatory Information
    "groups", "packagers", "manufacturers",
    # External References
    "external-identifiers", "external-links", "general-references",
    # Additional fields per your instructions
    "international-brands", "products"
}

def parse_drugbank_xml(xml_file):
    """
    Parses the DrugBank XML file and extracts key fields into a dictionary.
    Custom processing is applied for tags that contain sub-elements.
    """
    tree = etree.parse(xml_file, parser=etree.XMLParser())
    root = tree.getroot()
    id_to_info = {}

    # Select all drug elements (ignoring namespaces)
    drugs = root.xpath('./*[local-name()="drug"]')

    for drug in tqdm(drugs, desc="Processing drugs", unit="drug"):
        # Find the primary DrugBank ID
        drug_id_elements = drug.xpath('./*[local-name()="drugbank-id"][@primary="true"]')
        if not drug_id_elements:
            continue
        drug_id = drug_id_elements[0].text.strip()

        if valid_drugs and drug_id not in valid_drugs:
            continue

        drug_info = {}

        for child in drug:
            tag_name = child.tag.split('}')[-1]
            # Only process if tag is in desired_fields
            if desired_fields and tag_name not in desired_fields:
                continue

            # Custom processing for specific tags:
            if tag_name == "groups":
                # Collect text from each <group>
                groups = [sub_child.text.strip() for sub_child in child 
                          if sub_child.tag.split('}')[-1] == "group" and sub_child.text]
                if groups:
                    drug_info[tag_name] = groups

            elif tag_name == "general-references":
                ref_data = {}
                for sub in child:
                    sub_tag = sub.tag.split('}')[-1]
                    if sub_tag == "articles":
                        articles_list = []
                        for article in sub:
                            citation_elements = article.xpath("./*[local-name() = 'citation']")
                            if citation_elements and citation_elements[0].text:
                                articles_list.append(citation_elements[0].text.strip())
                        if articles_list:
                            ref_data["articles"] = articles_list
                    else:
                        # Default aggregation for other sub-tags in general-references
                        sub_texts = []
                        for sub_child in sub:
                            sub_child_tag = sub_child.tag.split('}')[-1]
                            sub_text = ''.join(sub_child.itertext()).strip()
                            if sub_text:
                                sub_texts.append(f"{sub_child_tag}: {sub_text}")
                        if sub_texts:
                            ref_data[sub_tag] = " | ".join(sub_texts)
                if ref_data:
                    drug_info[tag_name] = ref_data

            elif tag_name == "classification":
                class_data = {}
                for sub in child:
                    sub_tag = sub.tag.split('}')[-1]
                    text = sub.text.strip() if sub.text else ""
                    if text:
                        class_data[sub_tag] = text
                if class_data:
                    drug_info[tag_name] = class_data

            elif tag_name == "products":
                product_names = []
                # Iterate over each <product> element; extract only the <name> text.
                for product in child:
                    name_elems = product.xpath(".//*[local-name()='name']")
                    if name_elems and name_elems[0].text:
                        name_elem_text = name_elems[0].text.strip()
                        product_names.append(name_elem_text)
                    if len(product_names) >= 5:
                        break
                if product_names:
                    drug_info[tag_name] = product_names


            elif tag_name == "international-brands":
                brand_names = []
                for brand in child:
                    name_elems = brand.xpath(".//*[local-name()='name']")
                    if name_elems and name_elems[0].text:
                        name_elem_text = name_elems[0].text.strip()
                        brand_names.append(name_elem_text)
                if brand_names:
                    drug_info[tag_name] = brand_names


            elif tag_name == "categories":
                cat_list = []
                for cat in child:
                    inner_cat_elems = cat.xpath(".//*[local-name()='category']")
                    if inner_cat_elems and inner_cat_elems[0].text:
                        cat_text = inner_cat_elems[0].text.strip()
                        cat_list.append(cat_text)
                if cat_list:
                    drug_info[tag_name] = cat_list


            else:
                # Default processing: if element has children, concatenate their texts;
                # otherwise, use the element's text directly.
                if len(child) > 0:
                    sub_texts = []
                    for sub_child in child:
                        sub_tag = sub_child.tag.split('}')[-1]
                        sub_text = ''.join(sub_child.itertext()).strip()
                        if sub_text:
                            sub_texts.append(f"{sub_tag}: {sub_text}")
                    if sub_texts:
                        drug_info[tag_name] = " | ".join(sub_texts)
                else:
                    text = child.text.strip() if child.text else ""
                    if text:
                        drug_info[tag_name] = text

        id_to_info[drug_id] = drug_info

    return id_to_info
    
    
def save_prompt_to_file(prompt_text, filename="prompt_texts.txt"):
    with open(filename, "a", encoding="utf-8") as f:
        f.write(prompt_text + "\n\n")
        
def save_summary_prompt_to_file(summary_prompt, filename="summary_prompts.txt"):
    with open(filename, "a", encoding="utf-8") as f:
        f.write(summary_prompt + "\n\n")
        
def generate_general_references_table(links_text):
    """
    Given a string from the "links" field, this function splits the content by the pipe ("|")
    delimiter and builds a table with a numbered list.
    Expected format per reference:
      "link: L4539
       Electronic Medicines Compendium: Loteprednol etabonate Monograph
       https://www.medicines.org.uk/emc/product/6212"
    """
    items = links_text.split("|")
    rows = ""
    for i, item in enumerate(items, start=1):
        parts = item.strip().split("\n")
        if len(parts) >= 3:
            # The second line is assumed to be the reference title,
            # and the third line is the URL.
            title = parts[1].strip()
            url = parts[2].strip()
            link_html = f'<a href="{url}" target="_blank">[Link]</a>'
            rows += f"<tr><td>{i}. {title} {link_html}</td></tr>"
        else:
            rows += f"<tr><td>{i}. {item.strip()}</td></tr>"
    table_html = f"""
<table border="1" cellpadding="5" cellspacing="0">
  <thead>
    <tr><th>General References</th></tr>
  </thead>
  <tbody>
    {rows}
  </tbody>
</table>
"""
    return table_html
    
def generate_external_links_table(external_links_text):
    """
    Given a string from the "external-links" field, this function splits the content by the pipe ("|")
    delimiter and builds a table with two columns.
    Expected format per link:
      "external-link: RxList
       http://www.rxlist.com/cgi/generic2/lotemax.htm"
    In this example, the first column will contain the title (e.g. "RxList") and the second column the URL or identifier.
    """
    items = external_links_text.split("|")
    rows = ""
    for item in items:
        parts = item.strip().split("\n")
        if len(parts) >= 2:
            title = parts[0].replace("external-link:", "").strip()
            identifier = parts[1].strip()
            rows += f"<dt>{title}</dt><dd>{identifier}</dd>"
        else:
            rows += f"<dt></dt><dd>{item.strip()}</dd>"
    table_html = f"""
<section class="references">
  <h3>References</h3>
  <dl>
  <dt>External Links</dt>
    <dd><dl>{rows}</dl></dd>
  </dl>
  
</section>
"""
    return table_html

    
def generate_prompt(drug_info):
    """
    Constructs a detailed and professional prompt for GPT-4o using the extracted drug data.
    This prompt now includes additional fields such as groups, classification details, products,
    international brands, and categories.
    """
    # Prepare individual fields with fallback text if not available
    api_name = drug_info.get('name', 'N/A')
    cas_number = drug_info.get('cas-number', 'N/A')
    unii = drug_info.get('unii', 'N/A')
    physical_state = drug_info.get('state', 'N/A')
    avg_mass = drug_info.get('average-mass', 'N/A')
    mol_formula = drug_info.get('Molecular Formula', 'N/A')
    general_desc = drug_info.get('description', 'N/A')
    
    indication = drug_info.get('indication', 'N/A')
    pharmacodynamics = drug_info.get('pharmacodynamics', 'N/A')
    moa = drug_info.get('mechanism-of-action', 'N/A')
    metabolism = drug_info.get('metabolism', 'N/A')
    route_elim = drug_info.get('route-of-elimination', 'N/A')
    clearance = drug_info.get('clearance', 'N/A')
    absorption = drug_info.get('absorption', 'N/A')
    volume = drug_info.get('volume-of-distribution', 'N/A')
    half_life = drug_info.get('half-life', 'N/A')
    protein_binding = drug_info.get('protein-binding', 'N/A')
    toxicity = drug_info.get('toxicity', 'N/A')
    
    groups = ", ".join(drug_info.get('groups', [])) if isinstance(drug_info.get('groups'), list) else drug_info.get('groups', 'N/A')
    products = ", ".join(drug_info.get("products", [])) if "products" in drug_info else "N/A"
    
    logP = drug_info.get('logP', 'N/A')
    water_sol = drug_info.get('Water Solubility', 'N/A')
    smiles = drug_info.get('SMILES', 'N/A')
    
    classification = drug_info.get('classification', {})
    if isinstance(classification, dict) and classification:
        class_details = ", ".join([f"{key}: {value}" for key, value in classification.items()])
    else:
        class_details = 'N/A'
    
    categories = ", ".join(drug_info.get('categories', [])) if 'categories' in drug_info else 'N/A'
    
    intl_brands = ", ".join(drug_info.get('international-brands', [])) if 'international-brands' in drug_info else 'N/A'
    
    ext_links = drug_info.get('external-links', 'N/A')
    # For general references, we note that citation information is available but we don't include details.
    gen_refs = drug_info.get('general-references', 'N/A')
    
    fields = {
        "API Name": api_name,
        "CAS": cas_number,
        "State": physical_state,
        "General Description": general_desc,
        "Indication": indication,
        "Pharmacodynamics": pharmacodynamics,
        "Mechanism of Action": moa,
        "Metabolism": metabolism,
        "Absorption": absorption,
        "Approval Status and Groups": groups,
        "Classification": class_details,
        "Categories": categories,
        "International Brands": intl_brands,
        "References": gen_refs,
    }
    lines = [
        f"{label}: {value}"
        for label, value in fields.items()
        if value and value != 'N/A'
    ]
    data_block = "\n".join(lines)
    
    prompt = f"""
You are a seasoned pharmaceutical scientist. Your task is to write a sophisticated, comprehensive, and SEO-optimized description for API Product Dedicated Page on Pharmaoffer's platform. The description should be detailed (approximately 250-300 words), technically precise, and written in a tone that resonates with professional peers in the pharmaceutical industry. The description must be framed by the <p> tag. Use the following data to form description:
 {data_block}
"""
    save_prompt_to_file(prompt, "description_prompts.txt")
    return prompt

def validate_drug_data(drug_info):
    # Essential fields: name, description, pharmacodynamics
    missing = []
    for field in ['name']:
        if field not in drug_info or not drug_info[field]:
            missing.append(field)
    return missing

def generate_description(drug_info, max_retries=3):
    """
    Generates a unique API description using the new OpenAI client syntax.
    """
    prompt = generate_prompt(drug_info)
    retries = 0
    client = CLIENT
    while retries < max_retries:
        try:
            completion = client.chat.completions.create(
                model="gpt-5.1",
                messages=[
                    {"role": "developer", "content": "You are a PhD-level pharmaceutical scientist specializing in active pharmaceutical ingredients. Write 250–300 words of SEO-optimized API descriptions. Audience: formulation scientists, sourcing managers, CDMOs/CROs, and regulatory teams. Inside one <p> tag, provide a concise summary highlighting the main purpose and key features."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.4,
                max_tokens=600
            )
            description = completion.choices[0].message.content.strip()
            return description
        except Exception as e:
            print(f"Error generating description for drug {drug_info.get('name', 'Unknown')}: {e}")
            retries += 1
            time.sleep(2)
    return None
    
def generate_summary(description: str, max_retries: int = 3) -> str:
    """
    Generates a concise summary (1-2 sentences) from an existing description.
    """
    if not description:
        return "Summary not available."
    
    summary_prompt = f"""
Using the following key API data, produce a concise, professional summary in 1-2 sentences that highlights the most important about the drug API.
Description: {description}
"""
    retries = 0
    client = CLIENT
    while retries < max_retries:
        try:
            completion = client.chat.completions.create(
                model="gpt-5.1",
                messages=[
                    {
                        "role": "developer",
                        "content": "You are a PhD-level pharmaceutical scientist specializing in active pharmaceutical ingredients. Write a 1–2 sentence punchy summary."
                    },
                    {"role": "user", "content": summary_prompt}
                ],
                temperature=0.4,
                max_tokens=150,
            )
            summary = completion.choices[0].message.content.strip()
            save_summary_prompt_to_file(summary_prompt, "summary_prompts.txt")
            return summary
        except Exception as e:
            print(f"Error generating summary for drug {drug_info.get('name', 'Unknown')}: {e}")
            retries += 1
            time.sleep(2)
    return "Summary not available."
    
def remove_square_bracketed(text):
    # Remove any text enclosed in square brackets (non-greedy).
    return re.sub(r'\[.*?\]', '', text)

def generate_final_html(drug_info):
    """
    Generates the final HTML output by combining the AI-generated description
    with a structured, table-based representation of key drug data.
    Newline characters are removed and only available fields are output.
    Chemical Taxonomy is rendered as a 3-column table.
    (The output does not include outer <html> or <body> tags.)
    """
    # Generate main description and summary using earlier functions.
    main_desc = generate_description(drug_info)
    summary = generate_summary(main_desc)
    
    
# Build Identification rows (existing rows)
    identification_rows = ""
    if summary:
        identification_rows += f"<dt>Summary</dt><dd>{summary}</dd>"
    if "groups" in drug_info and drug_info["groups"]:
        groups = ", ".join(drug_info["groups"]) if isinstance(drug_info["groups"], list) else str(drug_info["groups"])
        identification_rows += f"<dt>Groups</dt><dd>{groups}</dd>"
    if "categories" in drug_info and drug_info["categories"]:
        categories_str = ", ".join(drug_info["categories"])
        identification_rows += f"<dt>Drug Categories</dt><dd>{categories_str}</dd>"
    # Brand names: Prefer international brands; otherwise, products.
    if "international-brands" in drug_info and drug_info["international-brands"]:
        brand_names = ", ".join(drug_info["international-brands"])
        identification_rows += f"<dt>Brand Names</dt><dd><em>{brand_names}</em></dd>"
    elif "products" in drug_info and drug_info["products"]:
        brand_names = ", ".join(drug_info["products"])
        identification_rows += f"<dt>Brand Names</dt><dd><em>{brand_names}</dd>"

    # Build Properties rows (to be integrated into the Identification table)
    properties_rows = ""
    if "state" in drug_info and drug_info["state"]:
        properties_rows += f"<dt>State</dt><dd>{drug_info.get('state')}</dd>"
    if "average-mass" in drug_info and drug_info["average-mass"]:
        properties_rows += f"<dt>Average Mass</dt><dd>{drug_info.get('average-mass')}</dd>"

    # If any properties exist, add a header row and then the properties rows.
    if properties_rows:
        identification_rows += f"<dt>Properties</dt><dd><dl>{properties_rows}</dl></dd>"

    # Finally, build the Identification table using the combined rows.
    identification_table = ""
    if identification_rows:
        identification_table = f"""
<section class="identification">
  <h3>Identification</h3>
  <dl>
    {identification_rows}
  </dl>
</section>
"""
    
    # Pharmacology table: Include only rows for available data.
    pharmacology_rows = ""
    if "indication" in drug_info and drug_info["indication"]:
        pharmacology_rows += f"<dt>Indication</dt><dd>{drug_info.get('indication')}</dd>"
    if "pharmacodynamics" in drug_info and drug_info["pharmacodynamics"]:
        pharmacology_rows += f"<dt>Pharmacodynamics</dt><dd>{drug_info.get('pharmacodynamics')}</dd>"
    if "mechanism-of-action" in drug_info and drug_info["mechanism-of-action"]:
        pharmacology_rows += f"<dt>Mechanism of Action</dt><dd>{drug_info.get('mechanism-of-action')}</dd>"
    if "absorption" in drug_info and drug_info["absorption"]:
        pharmacology_rows += f"<dt>Absorption</dt><dd>{drug_info.get('absorption')}</td></tr>"
    if "volume-of-distribution" in drug_info and drug_info["volume-of-distribution"]:
        pharmacology_rows += f"<dt>Volume of Distribution</dt><dd>{drug_info.get('volume-of-distribution')}</dd>"
    if "protein-binding" in drug_info and drug_info["protein-binding"]:
        pharmacology_rows += f"<dt>Protein Binding</dt><dd>{drug_info.get('protein-binding')}</dd>"
    if "metabolism" in drug_info and drug_info["metabolism"]:
        pharmacology_rows += f"<dt>Metabolism</dt><dd>{drug_info.get('metabolism')}</dd>"
    if "route-of-elimination" in drug_info and drug_info["route-of-elimination"]:
        pharmacology_rows += f"<dt>Route of Elimination</dt><dd>{drug_info.get('route-of-elimination')}</dd>"
    if "half-life" in drug_info and drug_info["half-life"]:
        pharmacology_rows += f"<dt>Half-life</dt><dd>{drug_info.get('half-life')}</dd>"
    if "clearance" in drug_info and drug_info["clearance"]:
        pharmacology_rows += f"<dt>Clearance</dt><dd>{drug_info.get('clearance')}</dd>"
    if "toxicity" in drug_info and drug_info["toxicity"]:
        pharmacology_rows += f"<dt>Toxicity</dt><dd>{drug_info.get('toxicity')}</dd>"
     
    pharmacology_table = ""
    if pharmacology_rows:
        pharmacology_table = f"""
<section class="pharmacology">
  <h3>Pharmacology</h3>
  <dl>
    {pharmacology_rows}
  </dl>
  
</section>
"""   

    
    # Chemical Taxonomy table with rowspan:
    chemical_taxonomy_table = ""
    if "classification" in drug_info and isinstance(drug_info["classification"], dict) and drug_info["classification"]:
        taxonomy_items = list(drug_info["classification"].items())
        if taxonomy_items:
            taxonomy_rows = ""
            for key, value in taxonomy_items:
                key_sentence = key[0].upper() + key[1:].lower() if key else ""
                taxonomy_rows += f"<dt>{key_sentence}</dt><dd>{value}</dd>"
            chemical_taxonomy_table = f"""
<section class="taxonomy">
  <h3>Chemical Taxonomy</h3>
  <dl>
    {taxonomy_rows}
  </dl>
  
</section>
"""
    
    general_refs_table = ""
    external_links_table = ""
    
    links_text = drug_info.get("links", "").strip()
    if links_text:
        general_refs_table = generate_general_references_table(links_text)
    
    ext_links_text = drug_info.get("external-links", "").strip()
    if ext_links_text:
        external_links_table = generate_external_links_table(ext_links_text)

    
    # Combine all parts along with the main description.
    final_html = f"<h3>General Description:</h3>{main_desc}<br>{identification_table}<br>{chemical_taxonomy_table}<br>{pharmacology_table}<br>{general_refs_table}<br>{external_links_table}"
    
    # Remove any text in square brackets from the final HTML.
    final_html = remove_square_bracketed(final_html)
    return final_html

def generate_xml_output(drug_data, final_descriptions, output_filename="api_descriptions.xml"):
    """
    Generates an XML file that contains the final HTML description for each drug.
    The structure is:
      <drugs>
        <drug>
          <name>...</name>
          <cas-number>...</cas-number>
          <description>[final generated HTML]</description>
        </drug>
        ...
      </drugs>
    """
    root = ET.Element("drugs")
    for drug_id, info in drug_data.items():
        # Only process drugs for which we have a final HTML description.
        if drug_id in final_descriptions:
            drug_elem = ET.SubElement(root, "drug")
            name_elem = ET.SubElement(drug_elem, "name")
            name_elem.text = info.get("name", "")
            cas_elem = ET.SubElement(drug_elem, "cas-number")
            cas_elem.text = info.get("cas-number", "")
            desc_elem = ET.SubElement(drug_elem, "description")
            # Optionally, if you want to preserve the HTML tags without escaping,
            # you could wrap it in a CDATA section. For now, we'll store as text.
            desc_elem.text = final_descriptions[drug_id]
    
    tree = ET.ElementTree(root)
    tree.write(output_filename, encoding="utf-8", xml_declaration=True)
    print(f"XML output saved to {output_filename}")


def main():
    xml_file = input("Enter the path to the Drugbank XML file (e.g., drugbank.xml): ").strip()
    if not os.path.exists(xml_file):
        print("File not found!")
        return

    print("Parsing XML and extracting drug data...")
    drug_data = parse_drugbank_xml(xml_file)
    
    with open("database.json", "w", encoding="utf-8") as f:
        json.dump(drug_data, f, ensure_ascii=False, indent=2)
    print(f"Parsing complete. Data saved to database.json with {len(drug_data)} drugs.")

    final_descriptions = {}
    for drug_id, info in tqdm(drug_data.items(), desc="Generating descriptions", unit="drug"):
        # Validate essential fields: name, description, and pharmacodynamics.
        missing_fields = []
        for field in ['name']:
            if field not in info or not info[field]:
                missing_fields.append(field)
        if missing_fields:
            print(f"Drug {drug_id} missing essential fields: {missing_fields}. Skipping.")
            continue

        final_html = generate_final_html(info)
        if final_html:
            final_descriptions[drug_id] = final_html
        else:
            print(f"Failed to generate description for drug {drug_id}.")

    with open("api_descriptions.json", "w", encoding="utf-8") as f:
        json.dump(final_descriptions, f, ensure_ascii=False, indent=2)
    print("Final API descriptions saved to api_descriptions.json")
    
     # Now, call the function to generate an additional XML file.
    generate_xml_output(drug_data, final_descriptions, output_filename="api_descriptions.xml")

if __name__ == "__main__":
    main()